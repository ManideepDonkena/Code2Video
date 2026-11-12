"""An MVQS-style spatial score (SGA, arXiv 2607.18116) for finished lessons, from the renderer's own scene graph.

SGA extracts a symbolic scene graph by partially executing generated Manim code and scores it at RESTING frames
(t = 0 and 1 of each animation). Our renderer lays each beat out once and the preview (``longform.preview.stills``)
saves the screen after every step, pause and beat end with manim's ``-s``: those ARE the resting states. A scratch
copy of ``runtime.py`` adds the scene graph (type and box of every visible object) to each still's record; run this
with ``PYTHONPATH=<that copy>``. No voice, no model, no money.

MVQS = 0.5 S_sp + 0.2 S_ly + 0.3 S_ed (SGA's weights; inner weights in SGA's listing order):
  S_sp = 0.50 overlap + 0.25 inside frame + 0.15 legible (text height >= 0.15) + 0.10 separation
  S_ly = 0.40 density (sum of areas / frame area, best in [0.10, 0.35]) + 0.60 distribution (4x3 cells occupied)
  S_ed = 0.40 labelling (a shape or mark has a text within 0.6 units) + 0.60 stills with no persistent conflict
Our reading where SGA gives no formula: severity weights 1 / 0.5 / 0.2; a text wholly inside a shape is intentional
(a label in its box); separation = mean nearest-neighbour centroid distance of texts over 10% of the diagonal, capped 1.
Labelling cannot use SGA's identifier match (we have no MathTex names per shape), so it uses nearness.

    PYTHONPATH=<scratch copy> python baseline/mvqs.py --out <dir> [--lessons id,id]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import baseline  # noqa: E402  (the corpus)

W, H = 14.222, 8.0


def _area(b):
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _inter(a, b):
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def score_still(graph, intent=False):
    """``intent``: our reading of SGA's "intentional patterns" for this renderer: a full-width band (the heading) is
    chrome, and a text over a large picture (a prepared drawing's printed label) is a label, not a conflict."""
    objs = [
        (k, b)
        for k, *b in graph
        if k != "Deco" and _area(b) > 1e-6 and not (intent and (b[2] - b[0]) > 0.95 * W and (b[3] - b[1]) < 0.15 * H)
    ]
    texts = [b for k, b in objs if k == "Text"]
    if not objs:
        return None
    conflicts, persistent = [], 0
    for i, (ki, bi) in enumerate(objs):
        for kj, bj in objs[i + 1 :]:
            if "Text" not in (ki, kj):
                continue
            inter = _inter(bi, bj)
            if inter <= 0:
                continue
            ri, rj = inter / _area(bi), inter / _area(bj)
            text_r = ri if ki == "Text" else rj
            other_k = kj if ki == "Text" else ki
            if other_k != "Text" and text_r > 0.98:  # a label wholly inside its shape: intentional
                continue
            if intent and other_k != "Text" and _area(bj if ki == "Text" else bi) > 0.15 * W * H:
                continue
            m = max(ri, rj)
            sev = 1.0 if m > 0.30 else 0.5 if m > 0.10 else 0.2
            conflicts.append(sev)
            persistent += sev >= 0.5
    overlap = 1 - min(1.0, sum(conflicts) / max(1, len(texts)))
    inside = sum(
        b[0] >= -W / 2 - 0.01 and b[2] <= W / 2 + 0.01 and b[1] >= -H / 2 - 0.01 and b[3] <= H / 2 + 0.01
        for _, b in objs
    ) / len(objs)
    legible = sum((b[3] - b[1]) >= 0.15 for b in texts) / len(texts) if texts else 1.0
    diag = math.hypot(W, H)
    cents = [((b[0] + b[2]) / 2, (b[1] + b[3]) / 2) for _, b in objs]
    seps = []
    for b in texts:
        c = ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
        d = [math.dist(c, o) for o in cents if o != c]
        if d:
            seps.append(min(1.0, min(d) / (0.1 * diag)))
    separation = sum(seps) / len(seps) if seps else 1.0
    s_sp = 0.5 * overlap + 0.25 * inside + 0.15 * legible + 0.10 * separation
    density = sum(_area(b) for _, b in objs) / (W * H)
    d_score = (
        1.0
        if 0.10 <= density <= 0.35
        else max(0.0, density / 0.10)
        if density < 0.10
        else max(0.0, 1 - (density - 0.35) / 0.35)
    )
    cells = set()
    for _, b in objs:
        for cx in range(4):
            for cy in range(3):
                cell = [-W / 2 + cx * W / 4, -H / 2 + cy * H / 3, -W / 2 + (cx + 1) * W / 4, -H / 2 + (cy + 1) * H / 3]
                if _inter(b, cell) > 0.02 * _area(cell):
                    cells.add((cx, cy))
    distribution = len(cells) / 12
    s_ly = 0.4 * d_score + 0.6 * distribution
    shapes = [b for k, b in objs if k in ("Geom", "Mark")]

    def near(a, b, gap=0.6):
        return not (a[2] + gap < b[0] or b[2] + gap < a[0] or a[3] + gap < b[1] or b[3] + gap < a[1])

    labelled = sum(any(near(s, t) for t in texts) for s in shapes) / len(shapes) if shapes else 1.0
    return {
        "s_sp": s_sp,
        "s_ly": s_ly,
        "labelled": labelled,
        "persistent": persistent,
        "conflicts": len(conflicts),
        "overlap": overlap,
        "inside": inside,
        "legible": legible,
        "density": density,
        "distribution": distribution,
        "objects": len(objs),
        "texts": len(texts),
    }


def mvqs(stills, intent=False):
    rows = [r for r in (score_still(s.get("graph") or [], intent) for s in stills) if r]
    if not rows:
        return None
    mean = lambda k: sum(r[k] for r in rows) / len(rows)  # noqa: E731
    anim = sum(r["persistent"] == 0 for r in rows) / len(rows)
    s_ed = 0.4 * mean("labelled") + 0.6 * anim
    total = 0.5 * mean("s_sp") + 0.2 * mean("s_ly") + 0.3 * s_ed
    return {
        "mvqs": round(100 * total, 2),
        "s_sp": round(100 * mean("s_sp"), 1),
        "s_ly": round(100 * mean("s_ly"), 1),
        "s_ed": round(100 * s_ed, 1),
        "stills": len(rows),
        "stills_with_conflict": sum(r["persistent"] > 0 for r in rows),
        "overlap": round(mean("overlap"), 3),
        "inside": round(mean("inside"), 3),
        "legible": round(mean("legible"), 3),
        "density": round(mean("density"), 3),
        "distribution": round(mean("distribution"), 3),
        "labelled": round(mean("labelled"), 3),
        "objects_per_still": round(mean("objects"), 1),
    }


def rescore(out):
    """Both readings again from the stored scene graphs (no render)."""
    results = json.loads((out / "mvqs.json").read_text(encoding="utf-8"))
    for lesson_id in results:
        try:
            stills = json.loads((out / lesson_id / "preview" / "preview.json").read_text(encoding="utf-8"))["stills"]
        except (OSError, ValueError, KeyError):
            continue
        results[lesson_id]["score"] = mvqs(stills)
        results[lesson_id]["score_intent"] = mvqs(stills, intent=True)
    (out / "mvqs.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    return results


def main():
    if "--rescore" in sys.argv:
        rescore(Path(sys.argv[sys.argv.index("--out") + 1]))
        return
    from lessonforge.longform import preview, runtime

    assert hasattr(runtime, "_scene_graph"), "run with PYTHONPATH set to the scratch copy that records the scene graph"
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--lessons", default="")
    args = parser.parse_args()
    out = Path(args.out)
    ids = [x for x in args.lessons.split(",") if x] or baseline.CORPUS
    import os

    env = {"PYTHONPATH": os.environ.get("PYTHONPATH", "")}
    results = {}
    for lesson_id in ids:
        work = out / lesson_id / "preview"
        try:
            seen = preview.stills(baseline.LESSONS / lesson_id, work=work, env=env, log=lambda *a: None)
            results[lesson_id] = {
                "score": mvqs(seen["stills"]),
                "probe_layout": len(seen["layout"]),
                "probe_bounds": len(seen["bounds"]),
                "failed_chapters": seen["failed"],
            }
        except Exception as exc:  # noqa: BLE001 - one lesson's failure is reported, the rest go on
            results[lesson_id] = {"error": f"{type(exc).__name__}: {exc}"}
        print(lesson_id, json.dumps(results[lesson_id])[:300], flush=True)
    (out / "mvqs.json").write_text(json.dumps(results, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
