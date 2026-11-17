"""Does the "blueprint" layout prompt give the local coder cleaner layouts, and videos that are read and teach better?

    python bench/blueprint_study.py [--workers 2]     -> runs/blueprint/qwen-blueprint/<slug>/ (videos, not in git),
                                                         bench/results/blueprint/{rows.json, report.json, report.md}
    python bench/blueprint_study.py --report

The blueprint prompt (generate.CODE_BLUEPRINT) makes the coder declare bands of the screen first, place every top-level
object at explicit coordinates, build rows as groups, keep one object per band, keep text short, and wrap what it
places in fit() (generate.FIT). Compared with family "qwen" of the generator study (bench/claude_gen.py):

  same       planner and coder (qwen3.6, qwen3-coder:30b), the plan itself (plan.json is copied from the qwen run), the
             quiz, the configuration (code check and safe patching from the first render), the admission check, the
             layout repair, the student and M9
  different  the coder's prompt, and the fit helper it may call

Layout of both versions is measured again here with one tracker (layout_study.layout_of), so counts are comparable.
M9 only (C2V_DENSE=0): the dense video is not asked. No repair loop.
"""

from __future__ import annotations

import argparse
import ast
import concurrent.futures as cf
import json
import os
import re
import shutil
import sys
from pathlib import Path

os.environ.setdefault("C2V_DENSE", "0")
os.environ.setdefault("C2V_STUDY", "blueprint")
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "bench")]

import claude_gen  # noqa: E402
import layout_study  # noqa: E402
from analyze import paired  # noqa: E402

from c2vlab import generate, layout, scene_graph  # noqa: E402

# Every number of this study was measured with the tracker as it was up to 2026-11-13. The default tracker changed on
# 2026-11-14 (scene_graph.V2); a resumed run stays comparable only on the old one. Re-measured on V2 once, by hand:
# bench/results/blueprint/tracker_v2.json.
scene_graph.V2 = False

FAMILY, REF = "qwen-blueprint", "qwen"
BASE = ROOT / "runs" / "blueprint"
REF_DIR = ROOT / "runs" / "claude-gen" / REF
OUT = ROOT / "bench" / "results" / "blueprint"
TEXT = ("Text", "MarkupText", "Paragraph", "Title")


def rules(video_dir):
    """How far the final code of a video follows the blueprint rules (counted from the code, nothing is run)."""
    out = {"sections": 0, "layout_comment": 0, "to_edge_or_corner": 0, "move_to_origin": 0, "unit_size": 0, "texts": 0,
           "long_texts": 0, "fit_calls": 0, "move_to_xyz": 0, "arrange": 0}  # fmt: skip
    for s in json.loads((video_dir / "sections.json").read_text()):
        code = (video_dir / "sections" / f"{s['id']}.py").read_text()
        out["sections"] += 1
        out["layout_comment"] += bool(re.search(r"#\s*LAYOUT\s*:", code))
        out["move_to_origin"] += len(re.findall(r"move_to\(\s*ORIGIN\s*\)", code))
        out["unit_size"] += len(re.findall(r"\bunit_size\s*=", code))
        out["move_to_xyz"] += len(re.findall(r"move_to\(\s*(?:\[|np\.array\(\[)", code))
        out["arrange"] += len(re.findall(r"\.arrange(?:_in_grid)?\(", code))
        try:
            tree = ast.parse(code)
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            name = n.func.id if isinstance(n.func, ast.Name) else n.func.attr if isinstance(n.func, ast.Attribute) else ""
            if name == "fit":
                out["fit_calls"] += 1
            if name == "to_corner":
                out["to_edge_or_corner"] += 1
            if name == "to_edge" and not (n.args and isinstance(n.args[0], ast.Name) and n.args[0].id == "UP"):
                out["to_edge_or_corner"] += 1  # to_edge(UP) is the title's exception
            if name in TEXT and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                text = n.args[0].value
                out["texts"] += 1
                out["long_texts"] += len(text) > 40 or len(text.split()) > 6
    return out


def measure_ref(slug):
    """The reference video of the same concept: layout measured now, with the tracker the blueprint video gets."""
    d = REF_DIR / slug
    plan = json.loads((d / "plan.json").read_text())
    return {"layout": layout_study.layout_of(d, plan), "rules": rules(d)}


REPEATS = {"qwen-plain-s1": (False, 100), "qwen-blueprint-s1": (True, 100)}  # family -> (blueprint prompt?, seed offset)


def rows_path(family):
    return OUT / ("rows.json" if family == FAMILY else f"rows_{family}.json")


def run(topics, workers, family=FAMILY):
    """One family. The repeats write every section again with another seed (the coder's seed plus the offset), so the
    spread between two runs of the SAME prompt can be set beside the difference between the prompts."""
    blueprint, offset = REPEATS.get(family, (True, 0))
    claude_gen.FAMILIES[family] = None  # a local family; nothing in claude_gen.py or its results is changed
    claude_gen.BASE = BASE
    generate.FEATURES = {"preflight", "safe_patch"} | ({"blueprint"} if blueprint else set())
    if offset:
        write = generate.write_code
        generate.write_code = lambda p, section, extra="", seed=0: write(p, section, extra, seed=seed + offset)
    layout.CROWDING = False  # as every family of the generator study
    cards = json.loads((ROOT / "bench" / "novel" / "cards.json").read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    path = rows_path(family)
    rows = {r["topic"]: r for r in json.loads(path.read_text())} if path.exists() else {}

    def job(topic):
        slug = generate.slug(topic)
        out = BASE / family / slug
        out.mkdir(parents=True, exist_ok=True)
        if not (out / "plan.json").exists():
            shutil.copy(REF_DIR / slug / "plan.json", out / "plan.json")  # the same plan: only the coder's prompt differs
        log = lambda m: print(f"[blueprint:{slug[:20]}] {m}", flush=True)
        row = claude_gen.one(family, topic, cards.get(topic), False, log)
        if "layout" in row:
            row["rules"] = rules(out)
            row["ref"] = measure_ref(slug)
        return row

    with cf.ThreadPoolExecutor(workers) as pool:
        futures = {pool.submit(job, t): t for t in topics if "teaching" not in rows.get(t, {})}
        for f in cf.as_completed(futures):
            topic = futures[f]
            try:
                rows[topic] = f.result()
                print(f"[blueprint] done {topic}", flush=True)
            except Exception as exc:  # noqa: BLE001 - one topic's failure is recorded, the rest go on
                rows[topic] = {"topic": topic, "family": family, "error": f"{type(exc).__name__}: {exc}"}
                print(f"[blueprint] FAILED {topic}: {exc}", flush=True)
            path.write_text(json.dumps(list(rows.values()), indent=1, ensure_ascii=False))


def report():
    rows = json.loads((OUT / "rows.json").read_text())
    ref = {r["slug"]: r for r in json.loads((ROOT / "bench/results/claude-gen" / f"rows_{REF}.json").read_text())}
    ok = [r for r in rows if "teaching" in r and r["slug"] in ref]
    tot = lambda rs, f: sum(f(r) for r in rs)
    adm = lambda r, k: r["admission"][k]
    rep = {"concepts": len(ok), "failed": [r["topic"] for r in rows if "teaching" not in r], "table": {}, "paired": {}}
    for name, mine, theirs in (
        ("Sections rendered on the first try", lambda r: adm(r, "rendered_first"), lambda r: adm(ref[r["slug"]], "rendered_first")),
        ("Sections clean on the first try", lambda r: adm(r, "ok_first"), lambda r: adm(ref[r["slug"]], "ok_first")),
        ("Sections in the final video", lambda r: r["layout"]["sections"], lambda r: r["ref"]["layout"]["sections"]),
        ("Videos clean after admission", lambda r: adm(r, "clean"), lambda r: adm(ref[r["slug"]], "clean")),
        ("Lasting conflicts", lambda r: r["layout"]["conflicts"], lambda r: r["ref"]["layout"]["conflicts"]),
        ("Timing faults", lambda r: r["layout"]["timing"], lambda r: r["ref"]["layout"]["timing"]),
        ("Broken attachments", lambda r: r["layout"]["broken_attachments"], lambda r: r["ref"]["layout"]["broken_attachments"]),
        *((f"Rule: {k.replace('_', ' ')}", (lambda r, k=k: r["rules"][k]), (lambda r, k=k: r["ref"]["rules"][k]))
          for k in ("layout_comment", "fit_calls", "move_to_xyz", "arrange", "to_edge_or_corner", "move_to_origin",
                    "unit_size", "texts", "long_texts")),
    ):  # fmt: skip
        rep["table"][name] = {"blueprint": tot(ok, mine), "plain": tot(ok, theirs)}
    for name, mine, theirs in (
        ("Layout score (MVQS)", lambda r: r["layout"]["mvqs_mean"] / 100, lambda r: r["ref"]["layout"]["mvqs_mean"] / 100),
        ("M9", lambda r: r["teaching"]["base"]["m9"], lambda r: ref[r["slug"]]["teaching"]["base"]["m9"]),
        ("Confidence with 3 frames", lambda r: r["teaching"]["base"]["s_frames_p"], lambda r: ref[r["slug"]]["teaching"]["base"]["s_frames_p"]),
    ):  # fmt: skip
        xs = [r for r in ok if mine(r) is not None and theirs(r) is not None]
        rep["paired"][name] = {"blueprint": sum(map(mine, xs)) / len(xs), "plain": sum(map(theirs, xs)) / len(xs),
                               "diff": paired([mine(r) for r in xs], [theirs(r) for r in xs])} if xs else None  # fmt: skip
    (OUT / "report.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False))
    md = [f"# Blueprint layout prompt against the plain prompt (local coder, {len(ok)} concepts, same plans)", "",
          "| | Blueprint | Plain |", "|---|---|---|"]  # fmt: skip
    md += [f"| {k} | {v['blueprint']} | {v['plain']} |" for k, v in rep["table"].items()]
    for k, v in rep["paired"].items():
        if v:
            md.append(f"| {k} | {100 * v['blueprint']:.1f} | {100 * v['plain']:.1f} |")
    md += ["", "Paired differences (blueprint minus plain):", ""]
    md += [f"- {k}: {json.dumps(v['diff'])}" for k, v in rep["paired"].items() if v]
    # every run of each prompt: the reference (plain, seed 0), the blueprint run above, and the repeats with another seed
    runs = {"plain, seed 0": [{"layout": r["ref"]["layout"], "admission": ref[r["slug"]]["admission"],
                               "teaching": ref[r["slug"]]["teaching"]} for r in ok],
            "blueprint, seed 0": ok}  # fmt: skip
    for fam, (blueprint, _) in REPEATS.items():
        if rows_path(fam).exists():
            runs[f"{'blueprint' if blueprint else 'plain'}, seed 1"] = [
                r for r in json.loads(rows_path(fam).read_text()) if "teaching" in r and r["slug"] in {x["slug"] for x in ok}]
    rep["runs"] = {name: {"videos": len(rs), "sections": tot(rs, lambda r: r["layout"]["sections"]),
                          "conflicts": tot(rs, lambda r: r["layout"]["conflicts"]),
                          "broken_attachments": tot(rs, lambda r: r["layout"]["broken_attachments"]),
                          "clean_videos": tot(rs, lambda r: r["admission"]["clean"]),
                          "mvqs": round(sum(r["layout"]["mvqs_mean"] for r in rs) / max(1, len(rs)), 1),
                          "m9": round(100 * sum(r["teaching"]["base"]["m9"] for r in rs) / max(1, len(rs)), 1),
                          "per_concept": {r.get("slug") or r["teaching"]["base"].get("topic", "?"):
                                          {"conflicts": r["layout"]["conflicts"], "broken": r["layout"]["broken_attachments"],
                                           "m9": r["teaching"]["base"]["m9"]} for r in rs if r.get("slug")}}
                   for name, rs in runs.items()}  # fmt: skip
    (OUT / "report.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False))
    md += ["", "## Every run (two seeds per prompt, when run)", "",
           "| Run | Videos | Sections | Lasting conflicts | Broken attachments | Clean videos | Layout score | M9 |", "|---|---|---|---|---|---|---|---|"]
    md += [f"| {k} | {v['videos']} | {v['sections']} | {v['conflicts']} | {v['broken_attachments']} | {v['clean_videos']} | {v['mvqs']} | {v['m9']} |"
           for k, v in rep["runs"].items()]
    if rep["failed"]:
        md += ["", f"No video: {', '.join(rep['failed'])}"]
    (OUT / "report.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--topics", default="")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--family", default=FAMILY, choices=[FAMILY, *REPEATS])
    args = ap.parse_args()
    if not args.report:
        admitted = list(json.loads((ROOT / "bench" / "novel" / "questions_admitted.json").read_text()))
        topics = [t.strip() for t in args.topics.split(",") if t.strip()] or admitted
        run([t for t in topics if (REF_DIR / generate.slug(t) / "plan.json").exists()], args.workers, args.family)
    report()


if __name__ == "__main__":
    main()
