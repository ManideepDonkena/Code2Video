"""TeachQuiz (Code2Video, arXiv 2510.01174) with the controls and the evidence check from our baseline study.

* The quiz is written from the TOPIC only (never from the video) and kept only where the student, with its own
  knowledge, gets it right AND the unlearned student with no video never does (3 seeds). It is split in two: DEV (feedback may look at it) and TEST (never seen by any repair).
* The student is told to forget the topic (shadow blocklist, NULL when the material does not teach it), then
  answers with nothing (S1) and with the video (S2). TQ = S2 - S1, on TEST.
* The video is shown as frames: 3 per section, at 40%, 70% and 95% of it (the student cannot take an mp4).
  `narration=True` adds each section's narration with its time (our videos are silent, as Code2Video's are).
* Controls: first section only, and another topic's video. A gain that does not fall on these is not teaching.
* Evidence: a right answer counts as backed only if the judge, shown the frame at the second the student cites
  and that section's text, says that moment teaches it.
"""

from __future__ import annotations

import json
import re
import subprocess

from . import llm

QUIZ = """Write a quiz that checks whether a student learned this topic. You are NOT shown any lesson.
Topic: {topic}. Students: class {grade}.
Write {n} multiple-choice questions, in English, at this level. Mix: recall, explain why, apply with small numbers,
read a picture described in words, a common misconception. Four options each, exactly one right, options short and
parallel, the right option not longer than the others, its letter varied.
Return JSON: {{"questions": [{{"id": "q1", "question": "...", "options": {{"A": "...", "B": "...", "C": "...",
"D": "..."}}, "answer": "A|B|C|D"}}]}}"""

KNOW = """Answer each multiple-choice question with your own knowledge.
Return JSON: {{"answers": [{{"id": "q1", "choice": "A|B|C|D"}}]}}

{questions}"""

UNLEARN = """You are a student who has NEVER learned the concept "{topic}".
Before answering, silently build a shadow-knowledge blocklist: every definition, alias, formula, rule, fact and worked
example that belongs to "{topic}" or to the ideas taught under it. You must not use anything on that list.
You may use only: (a) everyday knowledge a class {grade} student has that is NOT on the list, and (b) the evidence
in the attached material, if any. If a question needs blocked knowledge and the material does not supply it,
answer "NULL". Never guess."""

ANSWER = """{material}

QUESTIONS:
{questions}

For each question give your choice (A, B, C, D or NULL), the moment of the video that supplied the evidence as
mm:ss (null when none), and at most 15 words on why.
Return JSON: {{"answers": [{{"id": "q1", "choice": "A|B|C|D|NULL", "time": "mm:ss|null", "why": "..."}}]}}"""

EVIDENCE = """A student answered a quiz question from a lesson video and cited the second that taught the answer.
You get the question, the RIGHT answer, the text of the section playing at that second, and the frame at that second.
Does this moment TEACH or SHOW what is needed to choose the right answer? Quote what teaches it, then answer.
Return JSON: {{"quote": "...", "teaches": "yes|no"}}

{item}"""


def quiz_text(qs):
    return "\n\n".join(
        f"{q['id']}. {q['question']}\n" + "\n".join(f"  {k}) {v}" for k, v in q["options"].items()) for q in qs
    )


def make_quiz(topic, grade, out, n=24):
    path = out / "quiz.json"
    if path.exists():
        return json.loads(path.read_text())
    raw = llm.ask(llm.PLANNER, QUIZ.format(topic=topic, grade=grade, n=n), temperature=0.3, seed=7, note="quiz")
    raw = [q for q in raw.get("questions") or []
           if isinstance(q.get("options"), dict) and set(q["options"]) == set("ABCD") and q.get("answer") in "ABCD"]  # fmt: skip
    for i, q in enumerate(raw, 1):
        q["id"] = f"q{i}"
    solved = {
        a.get("id"): a.get("choice") for a in llm.ask(llm.STUDENT, KNOW.format(questions=quiz_text(raw)))["answers"]
    }
    known = [q for q in raw if solved.get(q["id"]) == q["answer"]]
    # Item filter: an item the UNLEARNED student gets right with no video measures guessing, not teaching
    # (our lessonforge baseline: 36% right with no video on an unfiltered quiz). Three seeds; right once = dropped.
    leaked = set()
    for seed in (1, 2, 3):
        leaked |= {a["id"] for a in student(topic, grade, known, seed=seed)["answers"] if a["right"]}
    kept = [q for q in known if q["id"] not in leaked]
    record = {"dev": kept[0::2], "test": kept[1::2], "written": len(raw), "known": len(known),
              "leaked": sorted(leaked), "kept": len(kept)}  # fmt: skip
    path.write_text(json.dumps(record, indent=1, ensure_ascii=False))
    return record


def stamp(s):
    return f"{int(s // 60):02}:{int(s % 60):02}"


def grab(video, t, path):
    if not path.exists():
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
                        "-vf", "scale=768:-2", "-q:v", "4", str(path)], check=True)  # fmt: skip
    return path


def frames_dir(run_dir):
    """Frames are cached per version of the video, so a revised video never reuses old frames."""
    folder = run_dir / "frames" / str(int((run_dir / "video.mp4").stat().st_mtime))
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def material(run_dir, narration=False, only_first=False):
    sections = json.loads((run_dir / "sections.json").read_text())
    if only_first:
        sections = sections[:1]
    folder = frames_dir(run_dir)
    images, labels, text = [], [], []
    for s in sections:
        for share in (0.4, 0.7, 0.95):
            t = s["start"] + share * (s["end"] - s["start"])
            images.append(grab(run_dir / "video.mp4", t, folder / f"{s['id']}_{int(share * 100)}.jpg"))
            labels.append(f"image {len(images)} at {stamp(t)}")
        if narration:
            text.append(f"[{stamp(s['start'])}-{stamp(s['end'])}] {s['narration']}")
    body = "FRAMES (in order): " + ", ".join(labels)
    if narration:
        body += "\nNARRATION:\n" + "\n".join(text)
    return images, body


def student(topic, grade, questions, images=(), body="", seed=1):
    reply = llm.ask(
        llm.STUDENT,
        ANSWER.format(material=body or "MATERIAL: none.", questions=quiz_text(questions)),
        images=images,
        system=UNLEARN.format(topic=topic, grade=grade),
        temperature=0.7,
        seed=seed,
        note="student",
    )
    got = {a.get("id"): a for a in reply.get("answers") or [] if isinstance(a, dict)}
    rows = []
    for q in questions:
        a = got.get(q["id"]) or {}
        choice = str(a.get("choice") or "NULL").strip().upper()[:4]
        rows.append(
            {
                "id": q["id"],
                "choice": choice,
                "right": choice == q["answer"],
                "time": a.get("time"),
                "why": a.get("why"),
            }
        )
    return {"score": round(100 * sum(r["right"] for r in rows) / max(1, len(rows)), 1), "answers": rows}


def seconds(value):
    m = re.match(r"\s*(\d+):(\d+)", str(value or ""))
    return int(m[1]) * 60 + int(m[2]) if m else None


def section_at(sections, t):
    return next((s for s in sections if s["start"] <= t < s["end"]), sections[-1] if sections else None)


def evidence(run_dir, questions, result):
    sections = json.loads((run_dir / "sections.json").read_text())
    end = sections[-1]["end"]
    key = {q["id"]: q for q in questions}
    ok = {}
    for r in result["answers"]:  # one call per item: asked for a list, the judge copies the template's ids
        t = seconds(r["time"])
        if not r["right"] or t is None or t > end + 1:
            continue
        s = section_at(sections, t)
        q = key[r["id"]]
        image = grab(run_dir / "video.mp4", min(t, end - 0.3), frames_dir(run_dir) / f"t{t:04}.jpg")
        item = (f"Cited {stamp(t)}\nQ: {q['question']}\nRIGHT ANSWER: {q['options'][q['answer']]}\n"
                f"SECTION TEXT: {s['teaches']} / {s['narration']}")  # fmt: skip
        reply = llm.ask(llm.JUDGE, EVIDENCE.format(item=item), images=[image], note="evidence")
        ok[r["id"]] = str(reply.get("teaches", "")).strip().lower().startswith("y")
    for r in result["answers"]:
        r["backed"] = bool(r["right"] and ok.get(r["id"]))
    result["evidence"] = round(100 * sum(r["backed"] for r in result["answers"]) / max(1, len(result["answers"])), 1)
    return result


def evaluate(run_dir, split="test", runs=3, narration=False, other=None):
    """TQ on one split, mean over `runs` students; controls on run 1 only."""
    plan = json.loads((run_dir / "plan.json").read_text())
    quiz = json.loads((run_dir / "quiz.json").read_text())
    qs = quiz[split]
    topic, grade = plan["topic"], plan["grade"]
    images, body = material(run_dir, narration)
    # seeds other than the item filter's (1-3), so S1 is not near zero by construction
    none = [student(topic, grade, qs, seed=10 + r) for r in range(1, runs + 1)]
    full = [evidence(run_dir, qs, student(topic, grade, qs, images, body, seed=r)) for r in range(1, runs + 1)]

    def mean(xs):
        return round(sum(xs) / len(xs), 1)

    out = {
        "split": split,
        "questions": len(qs),
        "none": mean([x["score"] for x in none]),
        "full": mean([x["score"] for x in full]),
        "evidence": mean([x["evidence"] for x in full]),
        "runs": {"none": none, "full": full},
    }
    out["teachquiz"] = round(out["full"] - out["none"], 1)
    first_images, first_body = material(run_dir, narration, only_first=True)
    out["control_first_section"] = student(topic, grade, qs, first_images, first_body)["score"]
    if other:
        o_images, o_body = material(other, narration)
        out["control_other_topic"] = student(topic, grade, qs, o_images, o_body)["score"]
    return out
