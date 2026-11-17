"""Topic -> plan -> one Manim scene per section -> rendered video. The Code2Video shape (planner, coder), kept small.

A run lives in one folder:
    plan.json           title + sections (what each teaches, what it shows, its narration)
    sections/sN.py      the Manim code of section N (class SN)
    video.mp4           the sections joined; sections.json gives each one's start and end
"""

from __future__ import annotations

import difflib
import json
import re
import subprocess
import sys
import time

from . import llm, preflight, temporal, timing
from .scene_graph import graph

PYTHON = sys.executable

PLAN = """Plan a short silent educational animation (Manim) that teaches: "{topic}" to class {grade} students.
Write {n} sections in teaching order. Each section is one scene of 15 to 25 seconds.
For each: what it teaches (one learning point), what is drawn and how it moves (concrete objects, numbers, labels),
and 2-3 sentences of narration that the on-screen text will carry.
Return JSON: {{"title": "...", "sections": [{{"id": "s1", "title": "...", "teaches": "...", "visual": "...",
"narration": "..."}}]}}"""

CODE = """Write Manim Community v0.20 code for ONE section of an educational video.

Video: {title}
Section {id}: {stitle}
It teaches: {teaches}
What to draw: {visual}
Narration (show its key words as short on-screen text, not whole sentences): {narration}
{extra}
Rules:
- Exactly: `from manim import *` then `class {cls}(Scene):` with `def construct(self):`. No other imports, no files.
- 15 to 25 seconds in total (sum of run_time and wait).
- Keep everything inside the frame (x in [-7, 7], y in [-3.9, 3.9]). Title at the top edge, small (font_size <= 36).
- Text never on top of other text or shapes: place with .next_to / .to_edge / .arrange, and FadeOut what is no
  longer needed before adding new things in the same place.
- Use Text for words; MathTex only for formulas. Font sizes 24 to 40.
- Give every object you show a variable name.
Return only the Python code."""

# Code2Video's layout (showlab/Code2Video, MIT licence: prompts/base_class.py and prompts/stage3.py): a fixed
# template with the title on top, short lecture lines fixed on the left, and a 6x6 grid of anchors (A1-F6) on the right
# where every animated object is placed. Used when "anchor" is in FEATURES (the anchor-layout study).
TEACHING_SCENE = """class TeachingScene(Scene):
    def setup_layout(self, title_text, lecture_lines):
        self.camera.background_color = "#000000"
        self.title = Text(title_text, font_size=28, color=WHITE).to_edge(UP)
        self.add(self.title)
        lecture_texts = [Text(line, font_size=22, color=WHITE) for line in lecture_lines]
        self.lecture = VGroup(*lecture_texts).arrange(DOWN, aligned_edge=LEFT).scale(0.8)
        self.lecture.to_edge(LEFT, buff=0.2)
        self.add(self.lecture)
        self.grid = {}
        rows = ["A", "B", "C", "D", "E", "F"]
        cols = ["1", "2", "3", "4", "5", "6"]
        for i, row in enumerate(rows):
            for j, col in enumerate(cols):
                self.grid[f"{row}{col}"] = np.array([0.5 + j * 1, 2.2 - i * 1, 0])

    def place_at_grid(self, mobject, grid_pos, scale_factor=1.0):
        mobject.scale(scale_factor)
        mobject.move_to(self.grid[grid_pos])
        return mobject

    def place_in_area(self, mobject, top_left, bottom_right, scale_factor=1.0):
        tl, br = self.grid[top_left], self.grid[bottom_right]
        mobject.scale(scale_factor)
        mobject.move_to(np.array([(tl[0] + br[0]) / 2, (tl[1] + br[1]) / 2, 0]))
        return mobject
"""

CODE_ANCHOR = """You are an expert Manim animator using Manim Community Edition. Write the Manim code for ONE section of an
educational video, using Code2Video's layout template.

Video: {title}
Section {id}: {stitle}
It teaches: {teaches}
What to animate: {visual}
Narration: {narration}
{extra}
1. Basic requirements:
- Use the TeachingScene base class below without modification; copy it into the file exactly.
- Lecture lines: write 2 to 4 short lecture lines (at most 7 words each) that carry the narration's key points.
- Each lecture line has a matching color with its animation elements. Apply ONLY color changes to lecture lines: no
  scaling, translation or Transform.

2. Visual anchor system (MANDATORY): a 6x6 grid (A1-F6) on the right side only.
lecture |  A1  A2  A3  A4  A5  A6
        |  B1  B2  B3  B4  B5  B6
        |  C1  C2  C3  C4  C5  C6
        |  D1  D2  D3  D4  D5  D6
        |  E1  E2  E3  E4  E5  E6
        |  F1  F2  F3  F4  F5  F6
- Point: self.place_at_grid(obj, 'B2', scale_factor=0.8). Area: self.place_in_area(obj, 'A1', 'C3', scale_factor=0.7).
- NEVER use .to_edge(), .move_to() or manual positioning for animated objects.
- Avoid occlusions; every label within 1 grid unit of its object; FadeOut what is no longer needed.

3. Structure, exactly:
from manim import *

{base}
class {cls}(TeachingScene):
    def construct(self):
        self.setup_layout("{stitle}", [... your lecture lines ...])
        # === Animation for Lecture Line 1 ===
        ...

4. Constraints: 15 to 25 seconds in total; light, distinguishable hexadecimal colors; Text for words, MathTex only for
formulas; no 3D, no files, no other imports. Give every object you show a variable name.
Return only the Python code."""

# Blueprint layout (the "typesetter" rules, 2026-11-14): the coder declares bands of the screen first, places every
# top-level object at explicit coordinates, builds rows as groups, keeps one object per band, and keeps text short.
# Used when "blueprint" is in FEATURES (bench/blueprint_study.py). `fit` is added to the file by ensure_fit, so the
# model never has to copy it.
FIT = """def fit(m, x=6.8, y=3.8):
    # keeps m inside the usable area: shrinks it if it is larger, then moves it back in
    if m.width > 2 * x or m.height > 2 * y:
        m.scale(0.98 * min(2 * x / max(m.width, 1e-6), 2 * y / max(m.height, 1e-6)))
    dx = max(-x - m.get_left()[0], 0) + min(x - m.get_right()[0], 0)
    dy = max(-y - m.get_bottom()[1], 0) + min(y - m.get_top()[1], 0)
    return m.shift([dx, dy, 0])
"""

CODE_BLUEPRINT = """Write Manim Community v0.20 code for ONE section of an educational video. Work like a typesetter:
decide where everything goes before you create any object.

Video: {title}
Section {id}: {stitle}
It teaches: {teaches}
What to draw: {visual}
Narration (show its key words as short on-screen text, not whole sentences): {narration}
{extra}
Rules:
- Exactly: `from manim import *` then `class {cls}(Scene):` with `def construct(self):`. No other imports, no files.
- 15 to 25 seconds in total (sum of run_time and wait).
- Use Text for words; MathTex only for formulas. Font sizes 24 to 40; the title small (font_size <= 36).
- Give every object you show a variable name.

Layout rules:
1. Blueprint first. The first line of construct is a comment that maps the screen into bands, for example
   # LAYOUT: title y=3.6 | row A y=2.0 | row B y=0.3 | key y=-3.4
   The frame is 14.2 wide and 8 high; the usable area is x in [-6.8, 6.8], y in [-3.8, 3.8].
   Never use to_edge, to_corner or move_to(ORIGIN). The only exception is the title: .to_edge(UP, buff=0.3).
   Place every top-level object with .move_to([x, y, 0]), using the coordinates of your LAYOUT line.
2. Group and drop. Build a row or a grid of items as VGroup(...).arrange(RIGHT, buff=0.3), then move_to the whole
   group once. Before you place a group, write its width as a comment (# width: 6 * 0.8 + 5 * 0.3 = 6.3) and keep it
   under 13. A sub-label is attached to its object: label.next_to(parent_object, DOWN, buff=0.15). next_to always
   takes an object, never a bare direction such as LEFT.
3. One occupant per band. A band holds one top-level object at a time. To put a new object where another one is, use
   ReplacementTransform(old, new), or FadeOut(old) in the step before. Do not write a label by hand where a built-in
   one already is (no Text at n2p(0) on a NumberLine that has include_numbers=True).
4. Sizes. Every Text has at most 6 words and 40 characters; never a whole sentence. NumberLine and Axes take length
   (or x_length and y_length), at most 12; never unit_size. Wrap every top-level object you place in fit(...):
   label = fit(Text("Result", font_size=30).move_to([0, 2.0, 0])). fit is already defined for you (it keeps an object
   inside the usable area); do not define it.
Return only the Python code."""


def ensure_fit(code):
    """The blueprint prompt lets the scene call fit(); the helper is put after the import when the file lacks it."""
    if "blueprint" not in FEATURES or "def fit(" in code or "fit(" not in code:
        return code
    head = "from manim import *"
    return code.replace(head, head + "\n\n\n" + FIT, 1) if head in code else FIT + "\n\n" + code


FIX_BLOCK = """This Manim section fails or has a layout fault. Fix ONLY the lines shown (lines {a} to {b}).

Problem: {problem}

Lines {a}-{b}:
{block}

Return JSON: {{"lines": "<the replacement for lines {a}-{b}, same indentation>"}}"""

FIX_WHOLE = """Rewrite this Manim section so it runs and has no layout faults. Keep what it teaches and shows.
{brief}
Problems:
{problem}

Code:
{code}

Return only the Python code (same class name {cls})."""


#: known Manim CE mistakes -> the fix (Code2Video's ScopeRefine keeps a table like this). Seen in our runs.
HINTS = [
    (
        r"getter\(\) takes 1 positional argument",
        (
            "That get_... method does not exist in Manim CE: Mobject turns unknown get_* names into attribute getters that "
            "take no arguments. Compute the value yourself (e.g. np.linalg.norm(p2 - p1) on get_vertices() points)."
        ),
    ),
    (
        r"has no attribute 'reverse'|has no attribute 'move_corner_to'|object has no attribute",
        (
            "That method does not exist on this Manim CE object. Use only documented methods (shift, move_to, next_to, "
            "scale, rotate, to_edge, set_color, become) or build the shape from points."
        ),
    ),
    (
        r"NoneType' and 'float'|NoneType' object",
        "A value is None: a helper returned nothing or a variable was never set. Compute coordinates as numpy arrays.",
    ),
    (
        r"list index out of range",
        "An index is past the end of a list (often get_vertices() or submobjects). Check the length before indexing.",
    ),
    (
        r"NameError: name '(\w+)' is not defined",
        "A name is used before it is defined, or a math symbol was written as Python. Define it, or put it in a string.",
    ),
    (
        r"latex|LaTeX|dvi",
        "LaTeX failed: use Text instead of MathTex for anything that is not a formula, and escape backslashes.",
    ),
]


#: pipeline features switched on for this process (bench/stages.py sets them; empty = the pilot's pipeline).
#: "brief" (2026-11-14): a whole-section rewrite is told what the section must teach and show, and a file that is
#: not code is written again from that brief instead of being patched.
FEATURES: set[str] = set()

#: hints added with the `preflight` feature (failure classes the pilot's table missed)
MORE_HINTS = [
    (r"could not broadcast|operands could not be broadcast", "Manim points are 3-D: write [x, y, 0], never (x, y)."),
    (r"could not find .*(svg|png|jpg)|no such file here", "There are no files: draw it from Manim shapes instead."),
    (r"does not accept the keyword", "Remove that keyword argument; set the property after creating the object."),
]


def hint(problem):
    table = HINTS + (MORE_HINTS if "preflight" in FEATURES else [])
    return next((h for pattern, h in table if re.search(pattern, problem)), "")


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48]


#: an invented concept (bench/novel): no model knows it, so every step that writes about it is given its card
SOURCE = """
This topic is NEW: no textbook or model knows it. Use exactly this definition, its rules, names and symbols, and
nothing that contradicts it:
{source}"""


FIELDS = ("title", "teaches", "visual", "narration")


def fix_keys(section):
    """The planner sometimes garbles a key ('narnarration'): give each missing field the closest spare key.
    Returns whether every field is now present."""
    for f in FIELDS:
        spare = [k for k in section if k not in FIELDS and k != "id"]
        if f not in section and (best := difflib.get_close_matches(f, spare, n=1, cutoff=0.6)):
            section[f] = section.pop(best[0])
    return all(f in section for f in FIELDS)


def plan(topic, grade, n, out, source=None):
    path = out / "plan.json"
    if path.exists():
        p = json.loads(path.read_text())
        before = json.dumps(p)
        fixed = [fix_keys(s) for s in p["sections"]]  # every section, not only up to the first failure
        if not all(fixed):
            raise ValueError(f"{path}: a section lacks one of {FIELDS}")
        if json.dumps(p) != before:
            path.write_text(json.dumps(p, indent=1, ensure_ascii=False))
        return p
    prompt = PLAN.format(topic=topic, grade=grade, n=n) + (SOURCE.format(source=source) if source else "")
    for seed in (3, 4, 5):
        p = llm.ask(llm.PLANNER, prompt, temperature=0.3, seed=seed)
        fixed = [fix_keys(s) for s in p.get("sections") or []]
        if fixed and all(fixed):
            break
    else:
        raise ValueError(f"{topic}: three plans, each with a section lacking one of {FIELDS}")
    for i, s in enumerate(p["sections"], 1):
        s["id"] = f"s{i}"
    p.update(topic=topic, grade=grade)
    if source:
        p["source"] = source
    out.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(p, indent=1, ensure_ascii=False))
    return p


def cls_of(section):
    return section["id"].upper()


def strip_fence(text):
    m = re.search(r"```(?:python)?\n(.*?)```", text, re.DOTALL)
    if not m and (cut := re.search(r"```(?:python)?\n", text)):
        return text[cut.end() :].strip() + "\n"  # a fence that never closes (a cut-off answer): drop the fence line
    return (m.group(1) if m else text).strip() + "\n"


def write_code(p, section, extra="", seed=0):
    template = CODE_ANCHOR if "anchor" in FEATURES else CODE_BLUEPRINT if "blueprint" in FEATURES else CODE
    text = llm.ask(
        llm.CODER,
        template.format(
            title=p["title"],
            id=section["id"],
            stitle=section["title"],
            teaches=section["teaches"],
            visual=section["visual"],
            narration=section["narration"],
            extra=extra + (SOURCE.format(source=p["source"]) if p.get("source") else ""),
            cls=cls_of(section),
            **({"base": TEACHING_SCENE} if "anchor" in FEATURES else {}),
        ),
        temperature=0.2,
        seed=seed,
        as_json=False,
    )
    return strip_fence(text)


def render(code_path, cls, media):
    """Render one section at low quality. Returns (mp4 path or None, error text)."""
    began = time.time()
    try:
        r = subprocess.run(
            [PYTHON, "-m", "manim", "-ql", "--media_dir", str(media), "--disable_caching", str(code_path), cls],
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except subprocess.TimeoutExpired:
        timing.log("render", code_path, cls, time.time() - began, False)
        return None, "render timed out after 600 s (an endless loop or a very long animation)"
    mp4 = media / "videos" / code_path.stem / "480p15" / f"{cls}.mp4"
    ok = r.returncode == 0 and mp4.exists()
    timing.log("render", code_path, cls, time.time() - began, ok)
    if ok:
        return mp4, ""
    return None, (r.stderr or r.stdout)[-3000:]


def error_line(err, code_path):
    """The last line of the section's own file in a traceback."""
    lines = re.findall(rf'{re.escape(code_path.name)}", line (\d+)', err)
    return int(lines[-1]) if lines else None


def patch_block(code, a, b, problem):
    """ScopeRefine's block scope: the model sees and replaces lines a..b only."""
    rows = code.splitlines()
    a, b = max(1, a), min(len(rows), b)
    block = "\n".join(f"{rows[i - 1]}" for i in range(a, b + 1))
    try:
        reply = llm.ask(llm.CODER, FIX_BLOCK.format(a=a, b=b, problem=problem[-1500:], block=block), temperature=0.1)
    except RuntimeError:
        return None  # a repair that cannot be had stands aside
    new = str(reply.get("lines") or "").rstrip("\n").splitlines()
    if not new:
        return None
    if "safe_patch" in FEATURES:  # a splice that does not parse would break the file: re-indent, else escalate
        return preflight.safe_splice(code, a, b, new)
    return "\n".join(rows[: a - 1] + new + rows[b:]) + "\n"


def brief_of(p, section, extra=""):
    """What a section must teach and show, as the coder was first told it (the `brief` feature)."""
    return (f"Video: {p['title']}\nSection {section['id']}: {section['title']}\nIt teaches: {section['teaches']}\n"
            f"What to draw: {section['visual']}\nNarration: {section['narration']}\n{extra}").strip()  # fmt: skip


def rewrite(code, cls, problem, brief=""):
    """ScopeRefine's section scope: the whole scene again, with the problems named. Without `brief` the model sees
    only the code; from code that was broken or cut off it then wrote a scene on another subject (2026-11-14), so
    build_section passes the brief when the `brief` feature is on. With brief "" the prompt is as it always was."""
    told = f"\nIt must still teach and show exactly this (the content does not change):\n{brief}\n" if brief else ""
    try:
        text = llm.ask(
            llm.CODER, FIX_WHOLE.format(problem=problem[-3000:], code=code, cls=cls, brief=told), temperature=0.2,
            as_json=False,
        )  # fmt: skip
    except RuntimeError:
        return None  # a repair that cannot be had stands aside
    return strip_fence(text)


def build_section(p, section, out, log=print, extra="", seed=0):
    """Write, render, and on failure repair line block -> whole section (at most 4 tries). Returns mp4 or None."""
    folder = out / "sections"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{section['id']}.py"
    cls = cls_of(section)
    if not path.exists() or extra:
        path.write_text(write_code(p, section, extra, seed=seed))
    history = []
    brief = brief_of(p, section, extra) if "brief" in FEATURES else ""
    for attempt in range(4):
        if "blueprint" in FEATURES and (given := path.read_text()) != (with_fit := ensure_fit(given)):
            path.write_text(with_fit)  # also after a repair that rewrote the file without the helper
        if "preflight" in FEATURES:  # F2 also fixes timing faults (c2vlab/temporal.py) before every render
            fixed, applied = temporal.fix(path.read_text())
            if applied:
                path.write_text(fixed)
                log(f"[gen] {section['id']}: timing fixes {[a['kind'] for a in applied]}")
        found = preflight.check(path.read_text()) if "preflight" in FEATURES else []
        if found:  # caught without rendering: repair it as if the render had failed there
            first = found[0]
            problem = "\n".join(f"line {f['line']}: {f['message']}" for f in found[:6])
            if hint(problem):
                problem += "\nHINT: " + hint(problem)
            line = first["line"]
            scope, reach = (("line", 2), ("block", 6), ("section", 0), ("section", 0))[attempt] if line else ("section", 0)
            if len(found) > 2 and scope != "section":
                scope = "section"  # many problems: one rewrite is cheaper than many patches
            history.append({"attempt": attempt, "ok": False, "line": line, "scope": scope, "preflight": True,
                            "error": problem[-400:]})  # fmt: skip
            log(f"[gen] {section['id']}: preflight {first['kind']} at line {line} ({first['message'][:70]}), repairing by {scope}")
            code = path.read_text()
            if brief and first["kind"] == "syntax" and (line or 1) <= 3:
                # not code at all (prose, or an answer cut off before it began): patching lines of it cannot help,
                # and a rewrite would be a guess. Write the section again from its brief.
                history[-1]["scope"] = "again"
                new = write_code(p, section, extra + "\nReturn ONLY the Python code, nothing before it.", seed=seed + attempt + 1)
            else:
                new = (rewrite(code, cls, problem, brief) if scope == "section"
                       else patch_block(code, line - reach, line + reach, problem))  # fmt: skip
            if new:
                path.write_text(new)
            continue
        mp4, err = render(path, cls, out / "media")
        if mp4:
            history.append({"attempt": attempt, "ok": True})
            (folder / f"{section['id']}.repairs.json").write_text(json.dumps(history, indent=1))
            return mp4
        # Manim's rich traceback hides the line; the partial execution (SGA) gives it plainly, in about a second
        crash = graph(path, cls, folder / f"{section['id']}.crash.json")["error"] or {}
        line = crash.get("line") or error_line(err, path)
        problem = f"{crash['type']}: {crash['message']}" if crash.get("type") else err
        if hint(problem):
            problem += "\nHINT: " + hint(problem)
        code = path.read_text()
        # ScopeRefine: the failing line and its neighbours, then a larger block, then the whole section
        scope, reach = (("line", 2), ("block", 6), ("section", 0), ("section", 0))[attempt] if line else ("section", 0)
        history.append({"attempt": attempt, "ok": False, "line": line, "scope": scope, "error": problem[-400:]})
        log(f"[gen] {section['id']}: render failed at line {line} ({problem[:80]}), repairing by {scope}")
        if scope == "section":
            new = rewrite(code, cls, f"line {line}: {problem}" if line else problem, brief)
        else:
            new = patch_block(code, line - reach, line + reach, problem)
        if new:
            path.write_text(new)
    if "blueprint" in FEATURES:
        path.write_text(ensure_fit(path.read_text()))
    if "preflight" in FEATURES and not preflight.check(path.read_text()):
        mp4, _ = render(path, cls, out / "media")  # the last repair is rendered too (the pilot's loop dropped it)
        history.append({"attempt": 4, "ok": bool(mp4)})
        if mp4:
            (folder / f"{section['id']}.repairs.json").write_text(json.dumps(history, indent=1))
            return mp4
    (folder / f"{section['id']}.repairs.json").write_text(json.dumps(history, indent=1))
    return None


def duration(mp4):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp4)],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(r.stdout.strip())


def join(out, p, clips):
    """Join section clips into video.mp4 and write sections.json (start, end of each)."""
    listing = out / "clips.txt"
    listing.write_text("".join(f"file '{c.resolve()}'\n" for c in clips.values()))
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy",
         str(out / "video.mp4")],
        check=True,
    )  # fmt: skip
    t, rows = 0.0, []
    for s in p["sections"]:
        if s["id"] in clips:
            d = duration(clips[s["id"]])
            rows.append({**s, "start": round(t, 2), "end": round(t + d, 2)})
            t += d
    (out / "sections.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False))
    return rows
