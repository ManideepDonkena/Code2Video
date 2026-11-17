"""Two checks that stay defined on a topic the student already knows, where M9 is not (c2vlab/dvgain.py).

  delivery   Can a viewer read what this video shows? The questions ask about the video's own content (which numbers
             its example uses, what a label says), written from the scene code, so knowing the topic does not answer
             them. Scored as M9 is: forced choice, both option orders, P(right) on 3 frames per section against no
             material, NVG = (S - B) / (1 - B).
  coverage   Is what the final quiz needs in the video at all? A judge that may know the topic looks at the same
             frames and says, for each TEST question, whether they show what is needed to choose the right answer.

Both have M9's control: the same questions on another topic's video (delivery should fall to 0, the judge should say
no). Neither says that a person learns from the video; they are the two things that must hold before one can.

A delivery question is kept only when (1) its `shown` text is found inside a string of the scene code, so the answer is
put on screen by the code, (2) a solver that reads the code (no frames) picks the keyed answer, and (3) the student
does not already answer it with no material (on option orders the score does not use, so the score never selects on
itself). Questions are asked ONE PER CALL: asked together they answer each other (a question naming "52" gives away
"which number glows?"; with no material the student went from P 0.01 alone to 0.99 in the batch).

Nothing is written into a run folder: every file goes to `store`, a folder of this study, so a copied run folder cannot
carry these answers to another video. Every probe file carries the hash of the quiz it answered.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import random
import re

from . import dvgain, llm, teachquiz

PER_SECTION = 4
KNOWN = 0.5  # a question the student answers with at least this P(right) and no material is left out
SELECT = (2, 3)  # option orders that choose the questions; the score uses dvgain.ROTATIONS, so it never selects on itself
WRITER = os.getenv("C2V_DELIVERY_WRITER", llm.PLANNER)
SOLVER = os.getenv("C2V_DELIVERY_SOLVER", llm.STUDENT)  # another model than the writer
COVERAGE_JUDGE = os.getenv("C2V_COVERAGE_JUDGE", llm.STUDENT)  # the strongest local model that reads images

WRITE = """Below is the Manim code of the {n} sections of a short lesson video on "{topic}". Write a quiz that checks
whether a viewer could READ what this video put on screen. You are testing the video, not the topic.

Write {k} multiple-choice questions for EACH section. Every question must
- ask about text this video shows in the body of the screen: the numbers of its worked example, a word or label it
  writes next to an object, a value inside a formula it displays. Never ask about a section title;
- have an answer that a person who knows the topic well but has NOT seen this video could not work out. Ask WHICH
  numbers, words or labels this video chose, never what a rule, a definition or a calculation gives.
  Good: "Which two numbers does the worked example in section s2 combine?"
  Bad: "What is the formula shown for the area?" (anyone who knows the topic can answer)
- not contain its own answer, and not be answered by another question;
- have four short options of the same kind (four numbers, four words), exactly one right. The wrong options must be as
  likely as the right one for someone who knows the topic: other numbers of the same size, other words that fit as
  well. Write options the way they look on screen (3 × 5), not as LaTeX code;
- carry "shown": the text that puts the right answer on screen, copied character for character from inside one
  Text, MathTex or Tex string of that section's code.

Return JSON: {{"questions": [{{"section": "s1", "question": "...", "options": {{"A": "...", "B": "...", "C": "...",
"D": "..."}}, "answer": "A|B|C|D", "shown": "..."}}]}}

{code}"""

SOLVE = """Below is the Manim code of a short lesson video, and a quiz about what the video shows on screen. Answer
each question from the code alone. If the code does not settle a question, or more than one option fits, answer NULL.
Return JSON: {{"answers": [{{"n": 1, "choice": "A|B|C|D|NULL"}}]}}

{code}

QUESTIONS:
{questions}"""

COVER = """These are {n} frames, in order, from a short lesson video on "{topic}".{card}

For each quiz question below, decide whether the frames SHOW what a viewer needs in order to choose the right answer:
the rule, the definition, or a worked example of the same kind. The right answer is given so that you know what to
look for. First quote the text on a frame (or describe the picture) that shows it, and give that frame's number. Say
"yes" only when you could quote it; when nothing on the frames shows it, the quote is empty and the answer is "no".

{items}

Return JSON: {{"answers": [{{"n": 1, "frame": 3, "quote": "...", "shown": "yes|no"}}]}}"""


def _norm(text):
    return re.sub(r"\s+", " ", str(text).replace("\\\\", "\\")).strip()


def strings(code):
    """Every string in the code (parts of f-strings included); when the code does not parse, what sits in quotes."""
    try:
        return [n.value for n in ast.walk(ast.parse(code)) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    except SyntaxError:
        return [a or b for a, b in re.findall(r'"([^"\n]*)"|\'([^\'\n]*)\'', code)]


def on_screen(shown, code):
    s = _norm(shown)
    return bool(s) and any(s in _norm(x) for x in strings(code))


def codes(video_dir):
    """Section id -> scene code, for the sections that are in the video."""
    out = {}
    for s in json.loads((video_dir / "sections.json").read_text()):
        path = video_dir / "sections" / f"{s['id']}.py"
        if path.exists():
            out[s["id"]] = path.read_text()
    return out


def _listing(code):
    return "\n\n".join(f"### section {sid}\n{text}" for sid, text in code.items())


def _well_formed(q, ids):
    opts = q.get("options")
    return (isinstance(opts, dict) and set(opts) == set("ABCD") and q.get("answer") in tuple("ABCD")
            and len({_norm(v).lower() for v in opts.values()}) == 4 and q.get("section") in ids
            and _norm(opts[q["answer"]]).lower() not in _norm(q.get("question", "")).lower())  # fmt: skip


def quiz(video_dir, topic, store, log=print):
    """The delivery quiz of one video, written once from its code (store/delivery_quiz.json)."""
    path = store / "delivery_quiz.json"
    if path.exists():
        return json.loads(path.read_text())
    store.mkdir(parents=True, exist_ok=True)
    code = codes(video_dir)
    raw = llm.ask(WRITER, WRITE.format(n=len(code), topic=topic, k=PER_SECTION, code=_listing(code)), temperature=0.3,
                  seed=7, note="delivery-quiz")  # fmt: skip
    raw = teachquiz.text_options([q for q in raw.get("questions") or [] if isinstance(q, dict)])
    formed = [shuffled(q) for q in raw if _well_formed(q, set(code))]
    shown = [q for q in formed if on_screen(q.get("shown", ""), code[q["section"]])]
    for i, q in enumerate(shown, 1):
        q["id"] = f"d{i}"
    solved = {}
    if shown:
        reply = llm.ask(SOLVER, SOLVE.format(code=_listing(code), questions=teachquiz.quiz_text(
            [{**q, "id": str(i)} for i, q in enumerate(shown, 1)])), note="delivery-solve")  # fmt: skip
        answers = [a for a in reply.get("answers") or [] if isinstance(a, dict)]
        by_n = {str(a.get("n")): a for a in answers}
        for i, q in enumerate(shown, 1):
            a = by_n.get(str(i)) or (answers[i - 1] if len(answers) == len(shown) and not by_n else {})
            solved[q["id"]] = str(a.get("choice") or "").strip().upper()[:1]
    valid = [q for q in shown if solved.get(q["id"]) == q["answer"]]
    prior = items(_probes(store / "dl_select.json", topic, valid, [], "MATERIAL: none.", SELECT)) if valid else {}
    kept = [q for q in valid if prior[q["id"]] < KNOWN]
    record = {"topic": topic, "written": len(raw), "well_formed": len(formed), "on_screen": len(shown),
              "solved": len(valid), "kept": len(kept), "writer": WRITER, "solver": SOLVER, "questions": kept,
              "dropped": [{**q, "why": f"answered without the video (P {prior[q['id']]:.2f})"} for q in valid if q not in kept]
              + [{**q, "why": "solver chose " + (solved.get(q["id"]) or "nothing")} for q in shown if q not in valid]
              + [{**q, "why": "shown text is not in the code"} for q in formed if q not in shown]}  # fmt: skip
    path.write_text(json.dumps(record, indent=1, ensure_ascii=False))
    log(f"[delivery] {video_dir}: {len(raw)} written, {len(shown)} on screen, {len(valid)} solved, {len(kept)} kept")
    return record


def shuffled(q):
    """The writer puts the right answer under A nearly every time; the options are dealt again (seeded by the question)."""
    texts = [q["options"][L] for L in "ABCD"]
    right = q["options"][q["answer"]]
    random.Random(q["question"]).shuffle(texts)
    return {**q, "options": dict(zip("ABCD", texts)), "answer": "ABCD"[texts.index(right)]}


def _key(questions):
    return hashlib.sha1(json.dumps([[q["id"], q["question"], q["options"], q["answer"]] for q in questions],
                                   sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]  # fmt: skip


def _probes(path, topic, questions, images, body, rotations=dvgain.ROTATIONS):
    """One call per question and option order. Calls on the same frames follow each other, so the server keeps the
    frames it has already read (1.3 s a call instead of 3.5 s)."""
    key = _key(questions) + f"|{len(images)}|" + "".join(map(str, rotations))
    if path.exists():
        old = json.loads(path.read_text())
        if old.get("quiz") == key:
            return old
    out = {"quiz": key, "frames": len(images), "rotations": []}
    for r in rotations:
        rows = [dvgain.probe(topic, [q], images, body, r) for q in questions]
        out["rotations"].append({"rotation": r, "items": [x["items"][0] for x in rows],
                                 "missing": sum(x["missing"] for x in rows)})  # fmt: skip
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    return out


def items(p):
    """Question id -> P(right), the mean over the option orders (a missing letter counts as chance)."""
    out = {}
    for r in p["rotations"]:
        for it in r["items"]:
            out.setdefault(it["id"], []).append(dvgain.CHANCE if it["p_right"] is None else it["p_right"])
    return {i: sum(v) / len(v) for i, v in out.items()}


def nvg_of(own, blind, keep=None):
    """NVG over the question ids in `keep` (all when None); None when nothing is left or no room above the prior."""
    ids = [i for i in own if i in blind and (keep is None or i in keep)]
    if not ids:
        return None
    return dvgain.nvg(sum(own[i] for i in ids) / len(ids), sum(blind[i] for i in ids) / len(ids))


def delivery(video_dir, topic, store, other_dir=None, quiz_from=None, log=print):
    """Delivery of one video. `quiz_from` is (video_dir, store) of the video whose quiz is asked: a layout variant
    shares its base's quiz and its no-material answers; a question whose `shown` text is no longer in this video's
    code is left out."""
    quiz_dir, quiz_store = quiz_from or (video_dir, store)
    record = quiz(quiz_dir, topic, quiz_store, log)
    code = codes(video_dir)
    qs = [q for q in record["questions"] if q["section"] in code and on_screen(q["shown"], code[q["section"]])]
    out = {"quiz": str(quiz_dir), "questions": len(qs), "written": record["written"], "solved": record["solved"]}
    if not qs:
        return {**out, "delivery": None, "control": None, "items": []}
    blind = items(_probes(quiz_store / "dl_blind.json", topic, record["questions"], [], "MATERIAL: none."))
    own = items(_probes(store / "dl_frames.json", topic, qs, *dvgain.material(video_dir, "frames")))
    other = None
    if other_dir is not None:
        other = items(_probes(store / "dl_other.json", topic, qs, *dvgain.material(other_dir, "frames")))
    mean = lambda d: sum(d[q["id"]] for q in qs) / len(qs)
    out.update(blind=mean(blind), own=mean(own), other=None if other is None else mean(other),
               delivery=nvg_of(own, blind, {q["id"] for q in qs}),
               control=None if other is None else nvg_of(other, blind, {q["id"] for q in qs}),
               items=[{**q, "p_blind": round(blind[q["id"]], 4), "p_own": round(own[q["id"]], 4),
                       "p_other": None if other is None else round(other[q["id"]], 4)} for q in qs])  # fmt: skip
    return out


def _judge(path, topic, questions, images, card):
    key = _key(questions) + COVERAGE_JUDGE
    if path.exists():
        old = json.loads(path.read_text())
        if old.get("quiz") == key:
            return old
    listing = "\n\n".join(f"{i}. {q['question']}\n   RIGHT ANSWER: {q['options'][q['answer']]}"
                          for i, q in enumerate(questions, 1))  # fmt: skip
    note = f"\nThe topic is new to you. This is its definition:\n{card}" if card else ""
    reply = llm.ask(COVERAGE_JUDGE, COVER.format(n=len(images), topic=topic, card=note, items=listing), images=images,
                    note="coverage")  # fmt: skip
    answers = [a for a in reply.get("answers") or [] if isinstance(a, dict)]
    by_n = {str(a.get("n")): a for a in answers}
    rows = []
    for i, q in enumerate(questions, 1):
        a = by_n.get(str(i)) or (answers[i - 1] if len(answers) == len(questions) else {})
        quote = str(a.get("quote") or "").strip()
        said = str(a.get("shown") or "").strip().lower().startswith("y")
        rows.append({"id": q["id"], "shown": bool(said and quote), "said": said, "frame": a.get("frame"),
                     "quote": quote[:300], "answered": bool(a)})  # fmt: skip
    out = {"quiz": key, "judge": COVERAGE_JUDGE, "frames": len(images), "items": rows}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    return out


def coverage(video_dir, topic_dir, store, other_dir=None):
    """Share of TEST questions whose need the judge finds on this video's frames, and on another topic's frames."""
    plan = json.loads((topic_dir / "plan.json").read_text())
    qs = json.loads((topic_dir / "quiz.json").read_text())["test"]
    share = lambda r: sum(x["shown"] for x in r["items"]) / max(1, len(r["items"]))
    own = _judge(store / "cv_own.json", plan["topic"], qs, dvgain.material(video_dir, "frames")[0], plan.get("source"))
    out = {"questions": len(qs), "coverage": share(own), "items": own["items"], "control": None}
    if other_dir is not None:
        other = _judge(store / "cv_other.json", plan["topic"], qs, dvgain.material(other_dir, "frames")[0],
                       plan.get("source"))  # fmt: skip
        out.update(control=share(other), other_items=other["items"])
    return out
