"""The idea under test: repair a generated video where a simulated, unlearned student failed to learn.

One round:
  1. The student answers the DEV quiz with the video (2 runs). A gap is a DEV question it got wrong or NULL in
     both runs, or got right only without a backed citation (the evidence judge says the cited moment does not
     teach it).
  2. The planner maps each gap to the section that should have taught it and says, in its own words, the idea that
     is missing. A missing idea that copies the question or an option (6 words in a row) is refused: the repair
     must teach the idea, not the item.
  3. Only those sections are written again (with the missing ideas), then layout-checked and rendered.
  4. The new video is kept only if DEV TeachQuiz does not fall and MVQS falls by less than 5 points.
TEST is never shown to any step; it is what the result is reported on.

Ablation ("generic"): the same number of sections, chosen without the student, are written again with "teach this
more clearly" (a critic-style revision with no learner signal). If it gains as much on TEST, the learner signal
adds nothing.
"""

from __future__ import annotations

import json
import re
import shutil

from . import generate, layout, llm, teachquiz

MAP = """A video teaching "{topic}" has these sections:
{sections}

A student who watched it could not answer these questions:
{questions}

For each question, which section should have taught what it needs, and what idea is missing from that section?
Write the missing idea in your own words as something to SHOW and SAY (an object, a number, a comparison), never by
repeating the question or its options. Return JSON: {{"gaps": [{{"id": "q1", "section": "s1", "missing": "..."}}]}}"""


def words(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def copies(a, b, n=6):
    wa, wb = words(a), words(b)
    grams = {tuple(wb[i : i + n]) for i in range(len(wb) - n + 1)}
    return any(tuple(wa[i : i + n]) in grams for i in range(len(wa) - n + 1))


def gaps(run_dir, quiz, runs=2):
    plan = json.loads((run_dir / "plan.json").read_text())
    images, body = teachquiz.material(run_dir)
    results = [
        teachquiz.evidence(run_dir, quiz["dev"], teachquiz.student(plan["topic"], plan["grade"], quiz["dev"], images, body, seed=r))
        for r in range(1, runs + 1)
    ]  # fmt: skip
    failed = [
        q
        for q in quiz["dev"]
        if not any(
            res["answers"][i]["backed"] for res in results for i, a in enumerate(res["answers"]) if a["id"] == q["id"]
        )
    ]
    return failed, results


def plan_fixes(plan, failed):
    if not failed:
        return {}
    sections = "\n".join(
        f"{s['id']}: {s['title']} - teaches {s['teaches']}; shows {s['visual']}" for s in plan["sections"]
    )
    reply = llm.ask(
        llm.PLANNER,
        MAP.format(topic=plan["topic"], sections=sections, questions=teachquiz.quiz_text(failed)),
        note="map",
    )
    by_id = {q["id"]: q for q in failed}
    fixes = {}
    for g in reply.get("gaps") or []:
        q = by_id.get(g.get("id"))
        missing = str(g.get("missing") or "").strip()
        if not q or g.get("section") not in {s["id"] for s in plan["sections"]} or not missing:
            continue
        if copies(missing, q["question"] + " " + " ".join(q["options"].values())):
            continue  # teaches the item, not the idea
        fixes.setdefault(g["section"], []).append(missing)
    return fixes


def revise(run_dir, new_dir, fixes, log=print):
    if new_dir.exists():
        shutil.rmtree(new_dir)
    shutil.copytree(run_dir, new_dir, ignore=shutil.ignore_patterns("frames", "round*", "generic*"))
    plan = json.loads((new_dir / "plan.json").read_text())
    clips, changed = {}, []
    kept = new_dir / "kept"
    kept.mkdir(exist_ok=True)
    for s in plan["sections"]:
        sid, folder = s["id"], new_dir / "sections"
        old_mp4 = new_dir / "media" / "videos" / sid / "480p15" / f"{sid.upper()}.mp4"
        mp4 = None
        if sid in fixes:
            # the incumbent is never lost: keep the old code, layout record and clip until the new one renders
            backup = {f: f.read_bytes() for f in (folder / f"{sid}.py", folder / f"{sid}.layout.json") if f.exists()}
            if old_mp4.exists():
                shutil.copy(old_mp4, kept / f"{sid}.mp4")
            extra = "This section must ALSO show and say:\n" + "\n".join(f"- {m}" for m in fixes[sid])
            if generate.build_section(plan, s, new_dir, log, extra=extra):
                layout.repair(sid, new_dir, log=log)
                mp4, _ = generate.render(folder / f"{sid}.py", sid.upper(), new_dir / "media")
            if mp4:
                changed.append(sid)
            else:
                log(f"[feedback] {sid}: the new version did not render; the old one stays")
                for path, data in backup.items():
                    path.write_bytes(data)
                if (kept / f"{sid}.mp4").exists():
                    shutil.copy(kept / f"{sid}.mp4", old_mp4)
        if not mp4 and old_mp4.exists():
            mp4 = old_mp4
        if mp4:
            clips[sid] = mp4
    generate.join(new_dir, plan, clips)
    return changed


def section_mvqs(run_dir):
    scores = []
    for p in sorted((run_dir / "sections").glob("s*.layout.json")):
        s = (json.loads(p.read_text()).get("score") or {}).get("mvqs")
        if s is not None:
            scores.append(s)
    return round(sum(scores) / len(scores), 2) if scores else None


def round_(run_dir, mode="learner", log=print):
    quiz = json.loads((run_dir / "quiz.json").read_text())
    plan = json.loads((run_dir / "plan.json").read_text())
    failed, _ = gaps(run_dir, quiz)
    fixes = plan_fixes(plan, failed)
    log(f"[feedback] {len(failed)} DEV gaps -> fixes for {sorted(fixes)}")
    if mode == "generic":
        n = max(1, len(fixes))
        fixes = {s["id"]: ["teach this section's point more clearly and completely"] for s in plan["sections"][:n]}
    if not fixes:
        return {"mode": mode, "kept": False, "reason": "no gaps"}
    new_dir = run_dir / ("round1" if mode == "learner" else "generic1")
    changed = revise(run_dir, new_dir, fixes, log)
    before = teachquiz.evaluate(run_dir, "dev", runs=2)
    after = teachquiz.evaluate(new_dir, "dev", runs=2)
    m0, m1 = section_mvqs(run_dir), section_mvqs(new_dir)
    kept = after["teachquiz"] >= before["teachquiz"] and (m0 is None or m1 is None or m1 > m0 - 5)
    report = {"mode": mode, "gaps": [q["id"] for q in failed], "fixes": fixes, "changed": changed, "dev_before": before["teachquiz"],
              "dev_after": after["teachquiz"], "mvqs_before": m0, "mvqs_after": m1, "kept": kept,
              "dir": str(new_dir)}  # fmt: skip
    (new_dir / "feedback.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    return report
