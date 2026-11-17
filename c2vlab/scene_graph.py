"""SGA's symbolic scene graph, without rendering (arXiv 2607.18116, "partial execution").

The section's construct() runs with Scene.play patched: every animation jumps to its end (begin, interpolate(1),
finish), so nothing is drawn and a scene runs in about a second. After each play the visible objects are recorded:
    kind   Text | Geom | Mark | Deco
    box    [x0, y0, x1, y1] in scene units (frame is 14.22 x 8)
    name   the variable in construct() that holds it (or its group), None if none
    line   the line in the section's file where the object was created
An exception stops the run but keeps the states recorded so far (SGA keeps partial graphs too).

Since 2026-11-14 (V2 = True; False gives the tracker as it was) the record also has:
    fill   the fill opacity (an unfilled circle drawn round a word is a highlight, not a shape on top of it)
    seg    [x0, y0, x1, y1], the two ends of a straight line or arrow (its box says nothing about where it runs)
    part   a number shared by the pieces of one axis, pair of axes or labelled brace (Manim lays these out itself)
and four corrections: an object morphed by Transform takes the kind and type of what it now shows (a Text morphed
into a circle was still scored as text); axes and labelled braces are opened, and the numbers of a number line are
objects of their own (a text on a tick number was hidden inside the axis box); what self.add puts on screen after
the last play is recorded as one more state.

    python -m c2vlab.scene_graph <section.py> <ClassName> <out.json> [v2]
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import sys
import time
import traceback
from pathlib import Path

TEXT = ("Text", "MarkupText", "Paragraph", "MathTex", "Tex", "SingleStringMathTex", "DecimalNumber", "Integer",
        "Variable", "Title", "BulletedList")  # fmt: skip
MARK = ("Arrow", "Vector", "DoubleArrow", "Line", "DashedLine", "Dot", "Brace", "BraceLabel", "Arc", "Angle",
        "RightAngle", "SurroundingRectangle", "Cross", "CurvedArrow", "TangentLine", "DashedVMobject")  # fmt: skip
DECO = ("NumberPlane", "BackgroundRectangle", "ScreenRectangle", "FullScreenRectangle")
GROUPS = ("VGroup", "Group", "VDict")
OPENED = ("Axes", "BraceLabel")  # containers whose parts are the objects a viewer sees (V2)
#: False: the tracker as it was up to 2026-11-13 (a study that must stay comparable with older graphs sets this)
V2 = True


def kind_of(mob):
    names = [c.__name__ for c in type(mob).__mro__]
    for k, table in (("Text", TEXT), ("Deco", DECO), ("Mark", MARK)):
        if any(n in table for n in names):
            return k
    return "Geom"


def visible(mob):
    for m in mob.family_members_with_points():
        try:
            if max(m.get_fill_opacity(), m.get_stroke_opacity()) > 0.05:
                return True
        except Exception:  # noqa: BLE001 - ImageMobject and friends have no opacity API
            return True
    return False


def box(mob):
    lo, hi = mob.get_corner([-1, -1, 0]), mob.get_corner([1, 1, 0])
    return [round(float(lo[0]), 3), round(float(lo[1]), 3), round(float(hi[0]), 3), round(float(hi[1]), 3)]


def leaves(mob):
    """Objects at SGA's level: a text or a shape is one object; groups are opened."""
    if type(mob).__name__ in GROUPS or (kind_of(mob) == "Geom" and type(mob).__name__ in ("VMobject", "Mobject")):
        for sub in mob.submobjects:
            yield from leaves(sub)
    else:
        yield mob


def parts(mob, became, part=None):
    """leaves() for the V2 tracker: (object, part). `became` holds what a Transform turned an object into; an object
    that now shows a text or a shape is one object even if it was built as a group."""
    if id(mob) in became and became[id(mob)][1] not in GROUPS:
        yield mob, part
        return
    names = [c.__name__ for c in type(mob).__mro__]
    if type(mob).__name__ in GROUPS or (kind_of(mob) == "Geom" and type(mob).__name__ in ("VMobject", "Mobject")):
        for sub in mob.submobjects:
            yield from parts(sub, became, part)
    elif kind_of(mob) != "Deco" and any(n in OPENED for n in names):
        for sub in mob.submobjects:
            yield from parts(sub, became, part or id(mob))
    elif kind_of(mob) != "Deco" and "NumberLine" in names:
        part = part or id(mob)
        yield mob, part
        for group in (getattr(mob, "numbers", None), getattr(mob, "labels", None)):
            for sub in getattr(group, "submobjects", None) or []:
                yield sub, part
    else:
        yield mob, part


def run(path, cls, out, v2=False):
    import manim
    from manim.animation.animation import prepare_animation

    created, names, states = {}, {}, []
    became, part_ids = {}, {}  # V2: id -> (kind, type) after a Transform; container id -> small number
    # `created` and `names` are keyed by id(). Python gives a freed object's id to a later one, which then inherited
    # the dead object's line or name (the same code gave 7, 10 and 11 conflicts). Every object recorded is kept alive.
    alive = {}
    target = str(path)

    def site():
        f = sys._getframe(2)
        while f is not None:
            if f.f_code.co_filename == target:
                return f
            f = f.f_back
        return None

    original_init = manim.Mobject.__init__

    def init(self, *a, **k):
        original_init(self, *a, **k)
        f = site()
        if f is not None:
            alive[id(self)] = self
            created.setdefault(id(self), f.f_lineno)

    manim.Mobject.__init__ = init

    def remember_names(frame):
        for var, val in frame.f_locals.items():
            if isinstance(val, manim.Mobject):
                names[id(val)] = var
                for m in val.get_family():
                    alive[id(m)] = m
                    names.setdefault(id(m), var)

    def snapshot(scene):
        objs = []
        for top in scene.mobjects:
            for m, part in parts(top, became) if v2 else ((x, None) for x in leaves(top)):
                if m.has_points() or m.submobjects:
                    if not visible(m):
                        continue
                    b = box(m)
                    kind, kind_type = became.get(id(m)) or (kind_of(m), type(m).__name__)
                    objs.append({"kind": kind, "box": b, "name": names.get(id(m)) or names.get(id(top)),
                                 "line": created.get(id(m)) or created.get(id(top)), "type": kind_type})  # fmt: skip
                    if not v2:
                        continue
                    o = objs[-1]
                    with contextlib.suppress(Exception):  # ImageMobject and friends have no opacity API
                        o["fill"] = round(float(m.get_fill_opacity()), 2)
                    if part is not None:
                        o["part"] = part_ids.setdefault(part, len(part_ids) + 1)
                    straight = [c.__name__ for c in type(m).__mro__]
                    if id(m) not in became and "Line" in straight and "NumberLine" not in straight:
                        with contextlib.suppress(Exception):  # a line with no points yet
                            a, e = m.get_start(), m.get_end()
                            o["seg"] = [round(float(v), 3) for v in (a[0], a[1], e[0], e[1])]
        return objs

    def record(scene, line):
        states.append({"after_line": line, "objects": snapshot(scene)})

    def morphed(scene, anims):
        """After Transform(a, b) the object on screen is still `a`, of a's class, drawn as b. Score it as b."""
        on_screen = {id(x) for x in scene.get_mobject_family_members()}
        for anim in anims:
            src, tgt = getattr(anim, "mobject", None), getattr(anim, "target_mobject", None)
            if src is None or tgt is None or src is tgt or id(src) not in on_screen or id(tgt) in on_screen:
                continue
            shown = getattr(anim, "target_copy", None) or tgt
            if type(shown) is type(src):
                continue  # .animate and MoveToTarget morph an object into a copy of itself
            for s, t in zip(src.get_family(), shown.get_family()):
                became[id(s)] = (kind_of(t), type(t).__name__)
            became[id(src)] = (kind_of(tgt), type(tgt).__name__)

    def play(self, *args, **kwargs):
        f = site()
        if f is not None:
            remember_names(f)
        anims = [prepare_animation(a) for a in args]
        self.add_mobjects_from_animations(anims)  # as Manim's own play: a copy being transformed joins the scene first
        for anim in anims:
            anim._setup_scene(self)
            anim.begin()
            anim.interpolate(1.0)
            anim.finish()
            anim.clean_up_from_scene(self)
        self.update_mobjects(0)
        if v2:
            morphed(self, anims)
        record(self, f.f_lineno if f is not None else None)

    manim.Scene.play = play
    manim.Scene.wait = lambda self, *a, **k: None

    error = None
    try:
        spec = importlib.util.spec_from_file_location("section", target)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        scene = getattr(module, cls)()
        scene.construct()
        if v2 and (last := snapshot(scene)) != (states[-1]["objects"] if states else []):
            states.append({"after_line": None, "objects": last})  # put on screen by self.add after the last play
    except Exception as exc:  # noqa: BLE001 - partial execution: keep what was recorded
        tb = traceback.extract_tb(exc.__traceback__)
        line = next((fr.lineno for fr in reversed(tb) if fr.filename == target), None)
        error = {"type": type(exc).__name__, "message": str(exc)[:500], "line": line}
    Path(out).write_text(json.dumps({"states": states, "error": error}, indent=1))


def graph(path, cls, out):
    """Run in a subprocess (Manim is patched in place) and return the recorded graph."""
    import subprocess

    from . import timing

    out = Path(out)
    out.unlink(missing_ok=True)  # never read the graph of an earlier version of the code
    began = time.time()
    try:
        r = subprocess.run(
            [sys.executable, "-m", "c2vlab.scene_graph", str(path), cls, str(out), *(["v2"] if V2 else [])],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
            cwd=str(Path(__file__).resolve().parents[1]),
        )
        stderr = r.stderr
    except subprocess.TimeoutExpired:
        stderr = "timed out after 180 s"
    try:
        g = json.loads(out.read_text())
    except (OSError, ValueError):
        g = {"states": [], "error": {"type": "Crash", "message": stderr[-500:], "line": None}}
    timing.log("scene_graph", path, cls, time.time() - began, not g.get("error"))
    return g


if __name__ == "__main__":
    run(Path(sys.argv[1]).resolve(), sys.argv[2], sys.argv[3], v2=sys.argv[4:5] == ["v2"])
