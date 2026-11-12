"""c2v-lab command line.

python run.py gen "Pythagoras theorem" --grade 8 [--sections 4]   plan, code, render, layout repair, join
python run.py layout runs/<slug>                                   scene graph + MVQS (+ repair) per section
python run.py quiz runs/<slug>                                     DEV / TEST quiz from the topic only
python run.py eval runs/<slug> [--split test] [--other runs/x]     TeachQuiz, evidence, controls, MVQS
python run.py feedback runs/<slug> [--mode learner|generic]        one learner-feedback round (or the ablation)
python run.py all "topic" --grade 8                                gen, quiz, eval, feedback, generic, eval both
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from c2vlab import feedback, generate, layout, llm, teachquiz

RUNS = Path(__file__).resolve().parent / "runs"


def gen(topic, grade, sections):
    out = RUNS / generate.slug(topic)
    p = generate.plan(topic, grade, sections, out)
    clips = {}
    for s in p["sections"]:
        if generate.build_section(p, s, out):
            layout.repair(s["id"], out)
            mp4, _ = generate.render(out / "sections" / f"{s['id']}.py", s["id"].upper(), out / "media")
            if mp4:
                clips[s["id"]] = mp4
        print(f"[gen] {s['id']} {'ok' if s['id'] in clips else 'FAILED'}")
    generate.join(out, p, clips)
    return out


def evaluate(run_dir, split, other=None):
    result = teachquiz.evaluate(run_dir, split, other=other)
    result["mvqs"] = feedback.section_mvqs(run_dir)
    (run_dir / f"eval_{split}.json").write_text(json.dumps(result, indent=1, ensure_ascii=False))
    print(json.dumps({k: v for k, v in result.items() if k != "runs"}, indent=1))
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["gen", "layout", "quiz", "eval", "feedback", "all"])
    ap.add_argument("target")
    ap.add_argument("--grade", default="8")
    ap.add_argument("--sections", type=int, default=4)
    ap.add_argument("--split", default="test")
    ap.add_argument("--other")
    ap.add_argument("--mode", default="learner", choices=["learner", "generic"])
    a = ap.parse_args()
    other = Path(a.other) if a.other else None

    if a.cmd == "gen":
        print(gen(a.target, a.grade, a.sections))
    elif a.cmd == "layout":
        run = Path(a.target)
        for p in sorted((run / "sections").glob("s*.py")):
            print(p.stem, layout.repair(p.stem, run)[0])
    elif a.cmd == "quiz":
        run = Path(a.target)
        plan = json.loads((run / "plan.json").read_text())
        q = teachquiz.make_quiz(plan["topic"], plan["grade"], run)
        print(f"written {q['written']}, kept {q['kept']} (dev {len(q['dev'])}, test {len(q['test'])})")
    elif a.cmd == "eval":
        evaluate(Path(a.target), a.split, other)
    elif a.cmd == "feedback":
        print(json.dumps(feedback.round_(Path(a.target), a.mode), indent=1))
    elif a.cmd == "all":
        run = gen(a.target, a.grade, a.sections)
        plan = json.loads((run / "plan.json").read_text())
        teachquiz.make_quiz(plan["topic"], plan["grade"], run)
        base = evaluate(run, "test", other)
        rows = {"baseline": {"test_tq": base["teachquiz"], "evidence": base["evidence"], "mvqs": base["mvqs"]}}
        for mode in ("learner", "generic"):
            r = feedback.round_(run, mode)
            if r.get("dir"):
                e = evaluate(Path(r["dir"]), "test", other)
                rows[mode] = {
                    "test_tq": e["teachquiz"],
                    "evidence": e["evidence"],
                    "mvqs": e["mvqs"],
                    "kept_by_dev": r["kept"],
                }
        rows["usd_spent"] = round(llm.spent(), 4)
        (run / "summary.json").write_text(json.dumps(rows, indent=1))
        print(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
