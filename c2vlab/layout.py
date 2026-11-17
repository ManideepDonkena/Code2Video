"""Layout check and repair for one section: SGA's scene graph + Code2Video's ScopeRefine escalation.

    level "shift"   (code, no model) put `name.shift(v)` before the play where the conflict appears, v = the
                    minimum separation vector. SGA hands this vector to the LLM; we try it as code first.
    level "block"   (model) lines around the object's creation, with the conflict and the vector named.
    level "section" (model) the whole scene again, with every conflict named.
Each try is kept only if it runs and is better (the incumbent is never lost). Better means fewer faults, or as many
faults and a higher MVQS. A fault is a lasting conflict or a crowding fault (mvqs.crowding: two texts nearer than
0.15 units, a text wider than the frame). MVQS alone kept shifts that cleared one overlap and left the text flush
against a third object, and it gave 88.9 to a section with a text 38 units wide. CROWDING = False gives the rule
used up to 2026-11-13 (lasting conflicts only, kept when MVQS goes up).

Since 2026-11-14 a try must also do no harm (SAFE; see accept()). The case that showed the need: a ring drawn round
the answer of a formula was called an overlap, the shift moved it onto the line of text above, and the move was kept
because MVQS went from 85.01 to 85.02 with one fault before and one after. A try is now refused when it leaves as
many faults and adds a new one, when the gain in MVQS is under MIN_GAIN, when a label or arrow comes loose from what
the code attached it to (attach.broken), when it leaves nothing on screen to measure, when it changes what is written
on screen, or when it drops an animation (showing less is the cheapest way to fewer faults).
"""

from __future__ import annotations

import ast
import json
import tempfile
from pathlib import Path

from . import attach, generate, mvqs
from .scene_graph import graph


def measure(path, cls, out):
    g = graph(path, cls, out)
    score = mvqs.mvqs(g["states"]) if g["states"] else None
    return g, (score or {}).get("mvqs", 0.0) if not g["error"] else 0.0, score


#: crowding faults count as faults in the repair, in admission and in the revision gate (False: the earlier rule)
CROWDING = True
PAD = 0.06  # a shift for two close texts clears mvqs.CLEAR by this much, so rounding cannot leave them close
#: a repair must do no harm to be kept (accept()). Only with CROWDING: CROWDING = False is the earlier rule, unchanged.
SAFE = True
MIN_GAIN = 0.5  # with as many faults as before, a try is kept only if MVQS rises by at least this much
BLANK = 1000  # what a section with nothing to measure counts as, in fault_count


def faults(states):
    """Lasting conflicts, then the crowding faults that are not among them, in the shape of a conflict."""
    out = mvqs.persistent_conflicts(states)
    if not CROWDING:
        return out
    pairs = {frozenset(((c["move"].get("name"), c["move"].get("line")), (c["stay"].get("name"), c["stay"].get("line"))))
             for c in out if c.get("stay")}  # fmt: skip
    for f in mvqs.crowding(states):
        a, b = f["obj"], f.get("other")
        if b is None:
            out.append({"crowding": "wide", "move": a, "stay": None, "vector": None, "after_line": f["after_line"]})
            continue
        if frozenset(((a.get("name"), a.get("line")), (b.get("name"), b.get("line")))) in pairs:
            continue  # two texts that overlap by more than 10% are already a lasting conflict
        move, stay = (a, b) if (a.get("line") or 0) >= (b.get("line") or 0) else (b, a)
        s = stay["box"]
        out.append({"crowding": "near", "gap": f["gap"], "move": move, "stay": stay, "after_line": f["after_line"],
                    "vector": mvqs.separation_vector(move["box"], [s[0] - PAD, s[1] - PAD, s[2] + PAD, s[3] + PAD])})  # fmt: skip
    return out


def rank(g, score):
    """What a repair must raise: fewer faults first, then MVQS. A scene that crashes ranks below every scene that
    runs (its graph stops early, so it would show fewer faults)."""
    if not CROWDING:
        return (0, score)
    if g["error"] or not g["states"] or (SAFE and mvqs.mvqs(g["states"]) is None):
        return (float("-inf"), 0.0)  # also a scene with nothing to measure: no object, so no fault, is not a repair
    return (-len(faults(g["states"])), score)


def _key(c):
    m, s = c["move"], c.get("stay") or {}
    kind = c.get("crowding") or ("outside" if c.get("outside") else "overlap")
    return (kind, frozenset(((m.get("name"), m.get("line")), (s.get("name"), s.get("line")))))


TEXTY = ("Text", "MathTex", "Tex", "MarkupText", "Paragraph", "Title", "BulletedList")


def written(code):
    """Every string a text-making call is given, with white space squeezed (a repair may break a line in two)."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in TEXTY:
            out += [(n.func.id, " ".join(a.value.split())) for a in n.args
                    if isinstance(a, ast.Constant) and isinstance(a.value, str)]  # fmt: skip
    return sorted(out)


def accept(old, new):
    """Is the try better than what we have? Each side is (code, graph, MVQS). The earlier rule was rank(new) >
    rank(old). With SAFE the try must also do no harm: see the module text."""
    (code0, g0, s0), (code1, g1, s1) = old, new
    if not (CROWDING and SAFE):
        return rank(g1, s1) > rank(g0, s0)
    if rank(g1, s1)[0] == float("-inf"):
        return False
    if rank(g0, s0)[0] == float("-inf"):
        return True  # what we have does not run or shows nothing; the try does
    if written(code0) is not None and written(code1) != written(code0):
        return False  # a repair moves things; it does not change, add or remove what is written on screen
    if len(g1["states"]) < len(g0["states"]):
        return False  # an animation was dropped (fewer objects is the cheapest way to fewer faults)
    if len(attach.broken(code1, g1)) > len(attach.broken(code0, g0)):
        return False  # a label or arrow came loose from what the code attached it to
    f0, f1 = faults(g0["states"]), faults(g1["states"])
    if len(f1) != len(f0):
        return len(f1) < len(f0)
    return not ({_key(c) for c in f1} - {_key(c) for c in f0}) and s1 >= s0 + MIN_GAIN


def fault_count(run_dir, sids):
    """Faults in the current code of these sections, measured now (a stored graph may be older than the code)."""
    n = 0
    with tempfile.TemporaryDirectory() as tmp:
        for sid in sids:
            path = Path(run_dir) / "sections" / f"{sid}.py"
            if path.exists():
                g, _, _ = measure(path, sid.upper(), Path(tmp) / f"{sid}.json")
                blank = SAFE and not g["error"] and mvqs.mvqs(g["states"]) is None
                n += BLANK if blank else len(faults(g["states"]))  # an emptied section must not pass as fault-free
    return n


def describe(c):
    m = c["move"]
    what = f'{m["type"]} "{m.get("name")}" (created line {m.get("line")}, box {m["box"]})'
    if c.get("crowding") == "wide":
        return (f"{what} is {m['box'][2] - m['box'][0]:.1f} units wide and the frame is {mvqs.W:.1f}: break its string "
                f"into lines with \\n so that no line is wider than 12 units; keep every word")  # fmt: skip
    if c.get("crowding") == "near":
        s = c["stay"]
        return (f'{what} is only {c["gap"]} units from {s["type"]} "{s.get("name")}" (line {s.get("line")}, box '
                f'{s["box"]}), so the two read as one text; moving it by {c["vector"]} would separate them')  # fmt: skip
    if c.get("outside"):
        return f"{what} is outside the frame; shift it by {c['vector']}"
    s = c["stay"]
    return (f'{what} overlaps {s["type"]} "{s.get("name")}" (line {s.get("line")}, box {s["box"]}) by '
            f"{int(100 * c['ratio'])}%; moving it by {c['vector']} would clear it")  # fmt: skip


def shift_patch(code, c):
    name, line = c["move"].get("name"), c.get("after_line")
    if not name or not line or not c.get("vector"):  # a text wider than the frame cannot be shifted inside
        return None
    if SAFE and CROWDING and name == (c.get("stay") or {}).get("name"):
        return None  # both are parts of one named group: shifting the group moves them together and clears nothing
    rows = code.splitlines()
    indent = rows[line - 1][: len(rows[line - 1]) - len(rows[line - 1].lstrip())]
    dx, dy = c["vector"]
    rows.insert(line - 1, f"{indent}{name}.shift({dx} * RIGHT + {dy} * UP)  # layout: separation vector")
    new = "\n".join(rows) + "\n"
    try:
        ast.parse(new)
    except SyntaxError:
        return None
    return new


def repair(section_id, out, rounds=3, log=print):
    path = out / "sections" / f"{section_id}.py"
    cls = section_id.upper()
    gpath = out / "sections" / f"{section_id}.graph.json"
    g, best, score = measure(path, cls, gpath)
    history = [{"level": "start", "mvqs": best, "conflicts": len(mvqs.persistent_conflicts(g["states"])),
                "faults": len(faults(g["states"]))}]  # fmt: skip
    for _ in range(rounds):
        found = faults(g["states"])
        if not found:
            break
        code = path.read_text()
        c = found[0]
        line = c["move"].get("line")
        tries = [("shift", shift_patch, (code, c))]
        if line:
            tries.append(("block", generate.patch_block, (code, line - 5, line + 5, describe(c))))
        tries.append(("section", generate.rewrite, (code, cls, "\n".join(describe(x) for x in found))))
        improved = False
        for level, make, args in tries:  # cheapest scope first (ScopeRefine)
            new = make(*args)
            if not new or new == code:
                continue
            path.write_text(new)
            g2, s2, score2 = measure(path, cls, gpath)
            if accept((code, g, best), (new, g2, s2)):
                log(f"[layout] {section_id}: {level} fix kept, faults {len(found)} -> {len(faults(g2['states']))}, "
                    f"MVQS {best:.1f} -> {s2:.1f}")  # fmt: skip
                history.append({"level": level, "mvqs": s2, "faults": len(faults(g2["states"])), "conflict": describe(c)})
                g, best, score, improved = g2, s2, score2, True
                break
            path.write_text(code)
        if not improved:
            history.append({"level": "none kept", "conflict": describe(c)})
            break
    g, _, _ = measure(path, cls, gpath)  # leave the graph of the kept code on disk
    (out / "sections" / f"{section_id}.layout.json").write_text(
        json.dumps({"score": score, "history": history, "conflicts": len(mvqs.persistent_conflicts(g["states"])),
                    "crowding": len(mvqs.crowding(g["states"]))}, indent=1)  # fmt: skip
    )
    return score, history
