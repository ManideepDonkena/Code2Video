"""MVQS (SGA, arXiv 2607.18116) over the recorded scene graph, and each conflict's minimum separation vector.

MVQS = 0.5 S_sp + 0.2 S_ly + 0.3 S_ed (SGA's weights; inner weights in SGA's listing order):
  S_sp = 0.50 overlap + 0.25 inside frame + 0.15 legible (text height >= 0.15) + 0.10 separation
  S_ly = 0.40 density (sum of areas / frame area, best in [0.10, 0.35]) + 0.60 distribution (4x3 cells occupied)
  S_ed = 0.40 labelling (a shape or mark has a text within 0.6) + 0.60 states with no persistent conflict
Where SGA gives no formula we chose: severity by coverage ratio (>0.30 high = 1, >0.10 medium = 0.5, else 0.2);
a text wholly inside a shape is a label in its box, not a conflict; separation = nearest-neighbour centroid distance
of texts over 10% of the diagonal, capped at 1.

Three cases are judged by more than boxes when the graph has the fields (scene_graph V2, 2026-11-14):
  highlight   an unfilled outline drawn after a text with its centre inside the text's box (a circle round the
              answer in a formula) is not a conflict. The repair used to move such a ring off its word.
  line        a straight line or arrow conflicts with a text only where the segment itself runs through the text's
              box (more than LINE_IN units). A diagonal arrow's box covers two empty corners, and a text in one of
              them was moved for no reason; a text wholly inside that box was excused even with the line through it.
              Two uses of a line on a text are meant and are not conflicts: the text sits on a filled plate that
              hides the line behind it (a "x" placed on an arrow), and a plain line drawn later through the middle
              of the text (crossing a term out).
  part        two pieces of one axis or labelled brace never conflict with each other (Manim places them).
"""

from __future__ import annotations

import math

W, H = 14.222, 8.0
GAP = 0.15
LINE_IN = 0.1  # a line conflicts with a text when more than this length of it lies inside the text's box


def area(b):
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def inter(a, b):
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def separation_vector(move, stay):
    """Smallest shift (dx, dy) that takes box `move` clear of box `stay`, staying inside the frame if it can."""
    options = [
        (stay[2] - move[0] + GAP, 0.0),
        (stay[0] - move[2] - GAP, 0.0),
        (0.0, stay[3] - move[1] + GAP),
        (0.0, stay[1] - move[3] - GAP),
    ]

    def inside(v):
        return (
            move[0] + v[0] >= -W / 2
            and move[2] + v[0] <= W / 2
            and move[1] + v[1] >= -H / 2
            and move[3] + v[1] <= H / 2
        )

    options.sort(key=lambda v: (not inside(v), abs(v[0]) + abs(v[1])))
    return [round(options[0][0], 2), round(options[0][1], 2)]


def inside_length(seg, b):
    """Length of the segment [x0, y0, x1, y1] that lies inside box b (Liang-Barsky clipping)."""
    x0, y0, x1, y1 = seg
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0 - b[0]), (dx, b[2] - x0), (-dy, y0 - b[1]), (dy, b[3] - y0)):
        if p == 0:
            if q < 0:
                return 0.0
        elif p < 0:
            t0 = max(t0, q / p)
        else:
            t1 = min(t1, q / p)
    return max(0.0, t1 - t0) * math.hypot(dx, dy)


def off_line(box, seg):
    """Smallest shift that takes the box clear of the line through seg, at right angles to the line."""
    x0, y0, x1, y1 = seg
    length = math.hypot(x1 - x0, y1 - y0) or 1.0
    nx, ny = -(y1 - y0) / length, (x1 - x0) / length
    d = ((box[0] + box[2]) / 2 - x0) * nx + ((box[1] + box[3]) / 2 - y0) * ny  # centre's signed distance from the line
    need = abs(nx) * (box[2] - box[0]) / 2 + abs(ny) * (box[3] - box[1]) / 2 + GAP - abs(d)
    side = 1.0 if d >= 0 else -1.0
    return [round(side * need * nx, 2), round(side * need * ny, 2)]


def meant(line, text, objs, run):
    """A line through a text that the scene intends: the text has a filled plate under it, or the line is a plain
    stroke drawn after the text, through its middle and across most of it (a term crossed out). `run` is the length
    of the line inside the text's box; a line that only clips a label on its way elsewhere is not excused."""
    t = text["box"]
    if any(o is not text and o["kind"] != "Text" and (o.get("fill") or 0) >= 0.5 and inter(o["box"], t) >= 0.9 * area(t)
           for o in objs):  # fmt: skip
        return True
    x0, y0, x1, y1 = line["seg"]
    mid = t[0] <= (x0 + x1) / 2 <= t[2] and t[1] <= (y0 + y1) / 2 <= t[3]
    across = run >= 0.6 * (t[2] - t[0])
    return (
        line["type"] in ("Line", "DashedLine") and mid and across and (line.get("line") or 0) >= (text.get("line") or 0)
    )


def highlight(shape, text):
    """An unfilled outline drawn after the text with its centre inside the text's box: a ring or box that marks
    (part of) the text. A shape that merely collides with a text has its centre outside the text's thin box.
    Needs the fill field; without it nothing is excused."""
    if shape.get("fill") is None or shape["fill"] > 0.05 or (shape.get("line") or 0) < (text.get("line") or 0):
        return False
    s, t = shape["box"], text["box"]
    return t[0] <= (s[0] + s[2]) / 2 <= t[2] and t[1] <= (s[1] + s[3]) / 2 <= t[3]


def conflicts(objects):
    """Text-involving overlaps in one resting state, with severity and a fix vector for the text."""
    found = []
    objs = [o for o in objects if o["kind"] != "Deco" and area(o["box"]) > 1e-6]
    for i, a in enumerate(objs):
        for b in objs[i + 1 :]:
            if "Text" not in (a["kind"], b["kind"]):
                continue
            if a.get("part") is not None and a.get("part") == b.get("part"):
                continue  # two pieces of one axis or labelled brace
            x = inter(a["box"], b["box"])
            if x <= 0:
                continue
            text, other = (a, b) if a["kind"] == "Text" else (b, a)
            ratio = max(x / area(a["box"]), x / area(b["box"]))
            sev = 1.0 if ratio > 0.30 else 0.5 if ratio > 0.10 else 0.2
            if other["kind"] != "Text" and other.get("seg"):  # a straight line: where it runs, not its box
                t = text["box"]
                run = inside_length(other["seg"], [t[0] + 0.03, t[1] + 0.03, t[2] - 0.03, t[3] - 0.03])
                if run <= LINE_IN or meant(other, text, objs, run):
                    continue
                ratio = min(1.0, run / max(t[2] - t[0], 1e-6))
                sev = 1.0 if ratio > 0.30 else 0.5
            elif other["kind"] != "Text" and x / area(text["box"]) > 0.98:
                continue  # a label wholly inside its shape
            elif other["kind"] != "Text" and highlight(other, text):
                continue  # a ring or box drawn round (part of) the text to mark it
            # move the later-created object (what was placed onto something already there)
            mover, stay = (a, b) if (a.get("line") or 0) >= (b.get("line") or 0) else (b, a)
            vector = separation_vector(mover["box"], stay["box"])
            if other["kind"] != "Text" and other.get("seg"):  # step off the line, not out of its whole box
                v = off_line(text["box"], other["seg"])
                vector = v if mover is text else [-v[0], -v[1]]
            found.append({"severity": sev, "ratio": round(ratio, 3), "move": mover, "stay": stay, "vector": vector})
    for o in objs:
        b = o["box"]
        if b[0] < -W / 2 - 0.01 or b[2] > W / 2 + 0.01 or b[1] < -H / 2 - 0.01 or b[3] > H / 2 + 0.01:
            dx = (-W / 2 - b[0] + GAP) if b[0] < -W / 2 else (W / 2 - b[2] - GAP) if b[2] > W / 2 else 0.0
            dy = (-H / 2 - b[1] + GAP) if b[1] < -H / 2 else (H / 2 - b[3] - GAP) if b[3] > H / 2 else 0.0
            found.append({"severity": 1.0, "ratio": None, "move": o, "stay": None, "vector": [round(dx, 2), round(dy, 2)],
                          "outside": True})  # fmt: skip
    return found


def score_state(objects):
    objs = [o for o in objects if o["kind"] != "Deco" and area(o["box"]) > 1e-6]
    if not objs:
        return None
    texts = [o["box"] for o in objs if o["kind"] == "Text"]
    cs = [c for c in conflicts(objects) if not c.get("outside")]
    overlap = 1 - min(1.0, sum(c["severity"] for c in cs) / max(1, len(texts)))
    inside = sum(
        o["box"][0] >= -W / 2 - 0.01 and o["box"][2] <= W / 2 + 0.01 and o["box"][1] >= -H / 2 - 0.01
        and o["box"][3] <= H / 2 + 0.01
        for o in objs
    ) / len(objs)  # fmt: skip
    legible = sum((b[3] - b[1]) >= 0.15 for b in texts) / len(texts) if texts else 1.0
    cents = [((o["box"][0] + o["box"][2]) / 2, (o["box"][1] + o["box"][3]) / 2) for o in objs]
    seps = []
    for b in texts:
        c = ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
        d = [math.dist(c, o) for o in cents if o != c]
        if d:
            seps.append(min(1.0, min(d) / (0.1 * math.hypot(W, H))))
    separation = sum(seps) / len(seps) if seps else 1.0
    density = sum(area(o["box"]) for o in objs) / (W * H)
    d_score = (
        1.0 if 0.10 <= density <= 0.35 else density / 0.10 if density < 0.10 else max(0.0, 1 - (density - 0.35) / 0.35)
    )
    cells = set()
    for o in objs:
        for cx in range(4):
            for cy in range(3):
                cell = [-W / 2 + cx * W / 4, -H / 2 + cy * H / 3, -W / 2 + (cx + 1) * W / 4, -H / 2 + (cy + 1) * H / 3]
                if inter(o["box"], cell) > 0.02 * area(cell):
                    cells.add((cx, cy))
    shapes = [o["box"] for o in objs if o["kind"] in ("Geom", "Mark")]

    def near(a, b, gap=0.6):
        return not (a[2] + gap < b[0] or b[2] + gap < a[0] or a[3] + gap < b[1] or b[3] + gap < a[1])

    return {
        "s_sp": 0.5 * overlap + 0.25 * inside + 0.15 * legible + 0.10 * separation,
        "s_ly": 0.4 * d_score + 0.6 * len(cells) / 12,
        "labelled": sum(any(near(s, t) for t in texts) for s in shapes) / len(shapes) if shapes else 1.0,
        "persistent": sum(c["severity"] >= 0.5 for c in cs),
    }


def mvqs(states):
    rows = [r for r in (score_state(s["objects"]) for s in states) if r]
    if not rows:
        return None

    def mean(k):
        return sum(r[k] for r in rows) / len(rows)

    s_ed = 0.4 * mean("labelled") + 0.6 * sum(r["persistent"] == 0 for r in rows) / len(rows)
    return {
        "mvqs": round(100 * (0.5 * mean("s_sp") + 0.2 * mean("s_ly") + 0.3 * s_ed), 2),
        "s_sp": round(100 * mean("s_sp"), 1),
        "s_ly": round(100 * mean("s_ly"), 1),
        "s_ed": round(100 * s_ed, 1),
        "states": len(rows),
        "states_with_conflict": sum(r["persistent"] > 0 for r in rows),
    }


CLEAR = 0.15  # two texts closer than this read as one run of glyphs (next_to's default buff is 0.25)


def crowding(states, clear=CLEAR):
    """Text faults the overlap test passes: two texts nearer than `clear` (touching boxes do not intersect, and an
    overlap under 10% is not a lasting conflict), and a text wider than the frame (moving it cannot bring it inside).
    Once each by object. Reported only: it is not part of MVQS and no gate reads it.

    On the 40 NOVEL-12 base sections (2026-11-13) it flags 10 sections that have no lasting conflict; Claude's fixer,
    which saw frames, fixed an overlap, crowding, off-screen or unreadable-text fault in 9 of them."""
    seen, out = set(), []

    def gap(a, b):
        dx = max(0.0, max(a[0], b[0]) - min(a[2], b[2]))
        dy = max(0.0, max(a[1], b[1]) - min(a[3], b[3]))
        return math.hypot(dx, dy)

    for s in states:
        texts = [o for o in s["objects"] if o["kind"] == "Text" and area(o["box"]) > 1e-6]
        for i, a in enumerate(texts):
            if a["box"][2] - a["box"][0] > W and ("wide", a.get("name"), a.get("line")) not in seen:
                seen.add(("wide", a.get("name"), a.get("line")))
                out.append({"fault": "wider than the frame", "obj": a, "after_line": s["after_line"]})
            for b in texts[i + 1 :]:
                key = ("near", a.get("name"), a.get("line"), b.get("name"), b.get("line"))
                if key not in seen and gap(a["box"], b["box"]) < clear:
                    seen.add(key)
                    out.append({"fault": "texts too close", "obj": a, "other": b,
                                "gap": round(gap(a["box"], b["box"]), 3), "after_line": s["after_line"]})  # fmt: skip
    return out


def persistent_conflicts(states):
    """Conflicts that a viewer sees at rest (medium or high, or outside the frame), once each by object pair."""
    seen, out = set(), []
    for s in states:
        for c in conflicts(s["objects"]):
            if c["severity"] < 0.5:
                continue
            key = (c["move"].get("line"), c["move"].get("name"), (c["stay"] or {}).get("line"), c.get("outside"))
            if key not in seen:
                seen.add(key)
                out.append({**c, "after_line": s["after_line"]})
    return out
