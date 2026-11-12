"""Baseline scores for finished lessons, with the metrics of Code2Video and SGA, judged by LOCAL vision models.

Nothing here is paid for: the student and the judges are models served by the box's own Ollama (no key, no ledger).
Nothing in a lesson folder is written; everything goes to ``<out>/<lesson id>/``.

Metrics (each named after where it comes from):

* TeachQuiz (Code2Video, arXiv 2510.01174 §4): a student told to "forget" the topic answers a multiple-choice quiz
  without the video (S1) and with it (S2); TQ = S2 - S1. Code2Video's student is Gemini 2.5 Pro watching the video;
  ours sees 16 evenly spaced frames and the timed transcript (a local model cannot take a video file).
* Shortcut controls (our benchmark doc, after the Agentic Benchmark Checklist): the same student with only the first
  12 seconds, with another lesson's video, with the voice only, with the pictures only. A score that does not fall
  on "first 12 s" and "other topic" is not measuring teaching.
* Evidence-checked accuracy (our doc of 2 Nov): an answer counts only when the second it cites teaches it. Here the
  judge (another model family) sees the transcript within 20 s of that second AND the frame at it.
* AES (Code2Video, five dimensions x 20 points) and SGA's VLM-judge dimensions (EL, AT, LF, VC, 0-100).
* Timing (our own, as in pilot/khan/compare.py): share of half-seconds in which the picture changes, spoken cues
  during which it changes ("claims covered"), speech over a still picture, words a minute, questions per 100 words.

The quiz is written from the lesson's BRIEF only (topic, class, goal), never from its script or video, and kept only
where a second model of another family answers it right with its own knowledge.

    python extras/lessonforge_baseline/baseline.py --out <dir> [--runs 3] [--lessons id,id]
        [--steps timing,quiz,student,evidence,judge,claude]
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures as cf
import json
import os
import random
import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

#: the lessonforge checkout whose finished lessons are scored (its workspace, its .env for the Claude judge)
ROOT = Path(os.getenv("LESSONFORGE_ROOT", "/home/mani/manim/lessonforge"))
LESSONS = ROOT / "lessonforge_workspace" / "lessons"
OLLAMA = "http://localhost:11434/api/chat"
#: writes the quiz from the brief; text only: on this box's Ollama it crashes with frames and a long transcript together
WRITER = "qwen3.6:latest"
STUDENT = (
    "gemma4:26b"  # the forgetting student, and the solver that keeps only quiz items it gets right with its knowledge
)
STUDENT2 = "qwen2.5vl:7b"  # a second student of another family
JUDGE = "qwen2.5vl:7b"  # evidence judge: another family than the student
JUDGES = ("gemma4:26b", "qwen2.5vl:7b")
FRAMES = 16
WINDOW = 20.0

#: one finished lesson per topic (the newest where a topic was made more than once); story scripts and demos left out
CORPUS = [
    "20261016-160309-0f3c8e",
    "20261012-104217-18bf87",
    "20261012-152335-2d27db",
    "20261010-083607-6afe02",
    "20261012-204215-146113",
    "20261012-191635-3ac7d0",
    "20261012-152306-902cc9",
    "20261012-104158-5d3fe6",
    "20261012-154827-79f310",
    "20261012-154813-a46b73",
    "20261009-121852-aee9fc",
    "20261010-083607-bc2147",
    "20261009-133243-c92dd1",
    "20261010-084003-f6f6c0",
    "20261016-153953-da0299",
    "20261012-201940-1ca014",
    "20261009-120614-a71f28",
    "20261009-200134-4aea9f",
    "20261009-203004-0979b9",
    "20261008-175632-89f7b0",
    "20261008-091501-1fec76",
]


# ── the model ────────────────────────────────────────────────────────────────────────────────────────────────────
def ask(model, prompt, images=(), system=None, temperature=0.0, seed=0, think=False, tries=6, ctx=32768):
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {
            "role": "user",
            "content": prompt,
            **({"images": [base64.b64encode(Path(i).read_bytes()).decode() for i in images]} if images else {}),
        }
    ]
    body = {
        "model": model,
        "stream": False,
        "think": think,
        "format": "json",
        "messages": messages,
        "options": {"temperature": temperature, "seed": seed, "num_ctx": ctx},
    }
    last = None
    for attempt in range(tries):
        try:
            request = urllib.request.Request(OLLAMA, json.dumps(body).encode(), {"Content-Type": "application/json"})
            reply = json.load(urllib.request.urlopen(request, timeout=900))
            text = reply["message"]["content"]
            return json.loads(text[text.find("{") : text.rfind("}") + 1])
        except Exception as exc:  # noqa: BLE001 - a bad reply is asked again, then reported
            last = exc
            time.sleep(5 + attempt * 10)  # a shared GPU box: a model may be reloading
    raise RuntimeError(f"{model}: no usable reply ({last})")


# ── a reference judge on the owner's Anthropic key (metered: ledger rows, hard cap) ─────────────────────────────
CLAUDE = "claude-haiku-5-5"
CLAUDE_CAP_USD = 1.50
_claude_spent = 0.0


def ask_claude(prompt, images=(), system=None):
    global _claude_spent
    from dotenv import dotenv_values
    from lessonforge import spend

    if _claude_spent >= CLAUDE_CAP_USD:
        raise RuntimeError("study cap for Claude reached")
    key = os.getenv("ANTHROPIC_API_KEY") or dotenv_values(ROOT / ".env").get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("no Anthropic key")
    content = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": base64.b64encode(Path(i).read_bytes()).decode(),
            },
        }
        for i in images
    ]
    content.append({"type": "text", "text": prompt + "\nAnswer with the JSON object only."})
    body = {
        "model": CLAUDE,
        "max_tokens": 4000,
        "messages": [{"role": "user", "content": content}],
        "output_config": {"effort": "low"},
        **({"system": system} if system else {}),
    }
    for attempt in range(4):
        try:
            began = time.time()
            request = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                json.dumps(body).encode(),
                {"Content-Type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"},
            )
            reply = json.load(urllib.request.urlopen(request, timeout=300))
            usage = reply.get("usage") or {}
            cost = (
                usage.get("input_tokens", 0) * 0.10
                + usage.get("output_tokens", 0) * 0.50
                + usage.get("cache_read_input_tokens", 0) * 0.01
            ) / 1e6
            _claude_spent += cost
            spend.record(
                "vision",
                "anthropic/" + CLAUDE,
                cost,
                prompt_tokens=usage.get("input_tokens", 0),
                completion_tokens=usage.get("output_tokens", 0),
                seconds=round(time.time() - began, 1),
                note="study-baseline",
                estimated=True,
            )
            text = "".join(b.get("text", "") for b in reply.get("content") or [] if b.get("type") == "text")
            return json.loads(text[text.find("{") : text.rfind("}") + 1])
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 401, 403):
                raise RuntimeError(f"Claude refused: {exc.code} {exc.read()[:200]!r}") from exc
            time.sleep(5 + attempt * 10)
        except (ValueError, OSError):
            time.sleep(5 + attempt * 10)
    raise RuntimeError("Claude: no usable reply")


# ── the lesson as material ──────────────────────────────────────────────────────────────────────────────────────
def stamp(seconds):
    return f"{int(seconds // 60):02}:{int(seconds % 60):02}"


def captions(path):
    cues, text = [], path.read_text(encoding="utf-8")
    for block in re.split(r"\n\s*\n", text):
        m = re.search(r"(\d+):(\d+):([\d.]+)\s+-->\s+(\d+):(\d+):([\d.]+)\s*\n(.+)", block, re.DOTALL)
        if m:
            a = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
            b = int(m[4]) * 3600 + int(m[5]) * 60 + float(m[6])
            cues.append((a, b, " ".join(m[7].split())))
    return cues


def frame(video, t, path, width=768):
    if not path.exists():
        subprocess.run(
            [
                "ffmpeg",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                f"{t:.2f}",
                "-i",
                str(video),
                "-frames:v",
                "1",
                "-vf",
                f"scale={width}:-2",
                "-q:v",
                "4",
                str(path),
            ],
            check=True,
        )
    return path


def material(lesson_id, out):
    root = LESSONS / lesson_id
    job = json.loads((root / "job.json").read_text(encoding="utf-8"))
    brief = job.get("brief") or {}
    checks = json.loads((root / "output" / "final_checks.json").read_text(encoding="utf-8"))
    video = root / "output" / checks["video"]
    duration = float(checks["duration_seconds"])
    folder = out / lesson_id / "frames"
    folder.mkdir(parents=True, exist_ok=True)
    times = [(i + 0.5) * duration / FRAMES for i in range(FRAMES)]
    frames = [frame(video, t, folder / f"f{i:02}.jpg") for i, t in enumerate(times)]
    early_times = [2.0, 6.0, 10.5]
    early = [frame(video, t, folder / f"e{i}.jpg") for i, t in enumerate(early_times)]
    cues = captions(root / "output" / "captions.vtt")
    return {
        "id": lesson_id,
        "root": root,
        "video": video,
        "duration": duration,
        "cues": cues,
        "topic": brief.get("topic") or job.get("title") or lesson_id,
        "grade": str(brief.get("grade") or ""),
        "goal": brief.get("goal") or "",
        "language": brief.get("language") or "",
        "frames": frames,
        "times": times,
        "early": early,
        "early_times": early_times,
    }


def transcript(cues, until=None):
    return "\n".join(f"[{stamp(a)}] {t}" for a, b, t in cues if until is None or a < until)


def shown(lesson, condition, other=None):
    """The images and the text the student is given in each condition."""
    if condition == "none":
        return [], ""
    if condition == "first12":
        return lesson["early"], _labels(lesson["early_times"]) + "\nTRANSCRIPT:\n" + transcript(lesson["cues"], 12.0)
    source = other if condition == "other" else lesson
    if condition == "voice":
        return [], "TRANSCRIPT:\n" + transcript(source["cues"])
    if condition == "pictures":
        return source["frames"], _labels(source["times"])
    return source["frames"], _labels(source["times"]) + "\nTRANSCRIPT:\n" + transcript(source["cues"])


def _labels(times):
    return "FRAMES (in order): " + ", ".join(f"image {i + 1} at {stamp(t)}" for i, t in enumerate(times))


# ── the quiz ────────────────────────────────────────────────────────────────────────────────────────────────────
QUIZ = """Write a quiz that checks whether a student learned this lesson. You are NOT shown the lesson, only its brief.

Topic: {topic}
Students: class {grade}
What the lesson must teach (its goal): {goal}

Write 12 multiple-choice questions, in English, at this class's level, that test ONLY what the goal says.
Mix the kinds: recall (2), explain why (3), apply with small numbers (3), read a picture described in words (2),
a common misconception (2). Prefer questions that need understanding of how something looks or changes, as a
teacher would draw it. Four options each, exactly one right, options short (one to eight words) and parallel,
the right option not longer than the others, and its letter varied across questions.
Return JSON: {{"questions": [{{"id": "q1", "kind": "recall|explain|apply|picture|misconception",
"question": "...", "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}}, "answer": "A|B|C|D"}}]}}"""

SOLVE = """Answer each multiple-choice question with your own knowledge. Return JSON:
{{"answers": [{{"id": "q1", "choice": "A|B|C|D"}}]}}

{questions}"""


def quiz_text(questions):
    return "\n\n".join(
        f"{q['id']}. {q['question']}\n" + "\n".join(f"  {k}) {v}" for k, v in q["options"].items()) for q in questions
    )


def make_quiz(lesson, out):
    path = out / lesson["id"] / "quiz.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    raw = ask(WRITER, QUIZ.format(**lesson), temperature=0.3, seed=7)["questions"]
    raw = [
        q
        for q in raw
        if isinstance(q.get("options"), dict) and set(q["options"]) == set("ABCD") and q.get("answer") in "ABCD"
    ]
    for i, q in enumerate(raw, 1):
        q["id"] = f"q{i}"
    solved = {a["id"]: a.get("choice") for a in ask(STUDENT, SOLVE.format(questions=quiz_text(raw)))["answers"]}
    kept = [q for q in raw if solved.get(q["id"]) == q["answer"]][:10]
    record = {
        "written": len(raw),
        "kept": len(kept),
        "dropped": [q["id"] for q in raw if solved.get(q["id"]) != q["answer"]],
        "questions": kept,
        "made_by": WRITER,
        "checked_by": STUDENT,
    }
    path.write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")
    return record


# ── the student (Code2Video's unlearn-then-relearn prompt, as the paper describes it) ─────────────────────────────
UNLEARN = """You are a student who has NEVER learned the concept "{topic}".
Before answering, silently build a shadow-knowledge blocklist: every definition, alias, formula, rule, fact and worked
example that belongs to "{topic}" or to the ideas taught under it. You must not use anything on that list.
You may use only: (a) everyday knowledge a class {grade} student would have that is NOT on the list, and (b) the
evidence in the attached material, if any (frames of the lesson video and its timed transcript).
Answers are evidence-gated: if a question needs blocked knowledge and the material does not supply it, write
"NULL" (INSUFFICIENT EVIDENCE). Never guess."""

ANSWER = """{material}

QUESTIONS:
{questions}

For each question give your choice (A, B, C, D or NULL), the moment of the video that supplied the evidence as
mm:ss (null when there was none), and at most 15 words on why.
Return JSON: {{"answers": [{{"id": "q1", "choice": "A|B|C|D|NULL", "time": "mm:ss|null", "why": "..."}}]}}"""

KNOW = """Answer each multiple-choice question with your own knowledge. Return JSON:
{{"answers": [{{"id": "q1", "choice": "A|B|C|D", "time": null, "why": "..."}}]}}

{questions}"""


def student(lesson, quiz, condition, run, other=None, model=STUDENT):
    images, text = shown(lesson, condition, other)
    questions = quiz_text(quiz["questions"])
    if condition == "know":  # no forgetting at all: what the student already knows (the leak's ceiling)
        reply = ask(model, KNOW.format(questions=questions), temperature=0.7, seed=run)
    else:
        reply = ask(
            model,
            ANSWER.format(material=text or "MATERIAL: none.", questions=questions),
            images=images,
            system=UNLEARN.format(**lesson),
            temperature=0.7,
            seed=run,
        )
    answers = {a.get("id"): a for a in reply.get("answers") or [] if isinstance(a, dict)}
    rows = []
    for q in quiz["questions"]:
        a = answers.get(q["id"]) or {}
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
    return {
        "condition": condition,
        "run": run,
        "model": model,
        "score": round(100 * sum(r["right"] for r in rows) / max(1, len(rows)), 1),
        "null": sum(r["choice"] == "NULL" for r in rows),
        "answers": rows,
    }


# ── evidence: does the cited second teach the answer? (words around it AND the frame at it) ───────────────────────
EVIDENCE = """A student answered quiz questions from a lesson video and cited the second that taught each answer.
For each item you get the question, the RIGHT answer, the transcript within 20 seconds of the cited second, and one
image: the frame at that second (image k belongs to item k).
Decide for each item: does this moment TEACH or SHOW what is needed to choose the right answer (yes), or could the
student only have known it from elsewhere (no)? Quote the words or describe what in the frame teaches it.
Return JSON: {{"items": [{{"id": "q1", "quote": "...", "teaches": "yes|no"}}]}}

{items}"""


def parse_time(value):
    m = re.match(r"\s*(\d+):(\d+)", str(value or ""))
    return int(m[1]) * 60 + int(m[2]) if m else None


def evidence(lesson, quiz, result, out, judge_model=JUDGE):
    key = {q["id"]: q for q in quiz["questions"]}
    items, images = [], []
    for row in result["answers"]:
        t = parse_time(row["time"])
        if not row["right"] or t is None or t > lesson["duration"] + 1:
            continue
        q = key[row["id"]]
        window = (
            transcript([c for c in lesson["cues"] if c[1] >= t - WINDOW and c[0] <= t + WINDOW]) or "(nothing said)"
        )
        images.append(
            frame(
                lesson["video"], min(t, lesson["duration"] - 0.5), out / lesson["id"] / "frames" / f"t{int(t):04}.jpg"
            )
        )
        items.append(
            f"ITEM {len(items) + 1} ({row['id']}), cited {stamp(t)}\nQ: {q['question']}\n"
            f"RIGHT ANSWER: {q['options'][q['answer']]}\nTRANSCRIPT:\n{window}"
        )
    supported = {}
    if items:
        prompt = EVIDENCE.format(items="\n\n".join(items))
        reply = ask_claude(prompt, images) if judge_model == CLAUDE else ask(judge_model, prompt, images=images)
        supported = {i.get("id"): str(i.get("teaches", "")).lower().startswith("y") for i in reply.get("items") or []}
    rows = result["answers"]
    backed = [r["right"] and supported.get(r["id"], False) for r in rows]
    tag = "" if judge_model == JUDGE else "_claude"
    for r, b in zip(rows, backed, strict=True):
        r["backed" + tag] = b
    result["evidence_score" + tag] = round(100 * sum(backed) / max(1, len(rows)), 1)
    result["cited"] = sum(1 for r in rows if r["right"] and parse_time(r["time"]) is not None)
    return result


# ── the judges: AES (Code2Video) and SGA's VLM dimensions ────────────────────────────────────────────────────────
AES = """You are an expert educational content evaluator specializing in instructional videos.
Evaluate this lesson video on "{topic}" (class {grade}) from its frames (in order, evenly spaced) and its timed
transcript. Score five dimensions, each out of 20:
- Element Layout: placement, spacing, no overlap or clipping, use of the frame
- Attractiveness: visual appeal, colour, style, engagement
- Logic Flow: order of ideas, transitions, build-up from simple to complex
- Accuracy & Depth: correctness of content and appropriate depth for the audience
- Visual Consistency: consistent style, notation and colours across the video
Return JSON: {{"element_layout": {{"score": 0, "feedback": "..."}}, "attractiveness": {{...}}, "logic_flow": {{...}},
"accuracy_depth": {{...}}, "visual_consistency": {{...}}, "overall": 0, "strengths": ["..."], "improvements": ["..."]}}

{material}"""

SGA = """Rate this educational animation on "{topic}" from its frames and transcript, each 0-100:
- Educational Logic: does the sequence explain the concept correctly and clearly?
- Aesthetic Tone: is it visually pleasant and coherent in style?
- Layout Flow: are elements placed without overlap, inside the frame, and do they move sensibly between frames?
- Visual Clarity: is every label, number and object readable and unambiguous?
Return JSON: {{"educational_logic": 0, "aesthetic_tone": 0, "layout_flow": 0, "visual_clarity": 0, "notes": "..."}}

{material}"""

AES_KEYS = ["element_layout", "attractiveness", "logic_flow", "accuracy_depth", "visual_consistency"]
SGA_KEYS = ["educational_logic", "aesthetic_tone", "layout_flow", "visual_clarity"]


def _norm(d):
    """Keys as letters only, so "Element Layout", "element_layout" and "elementLayout" are one key."""
    return {re.sub(r"[^a-z]", "", str(k).lower()): v for k, v in (d or {}).items()} if isinstance(d, dict) else {}


def judge(lesson, model, run):
    images, text = shown(lesson, "full")
    asker = (
        (lambda p: ask_claude(p, images))
        if model == CLAUDE
        else (lambda p: ask(model, p, images=images, temperature=0.2, seed=run))
    )
    aes = asker(AES.format(material=text, **lesson))
    if isinstance(aes.get("scores"), dict):
        aes = {**aes, **aes["scores"]}
    aes_n = _norm(aes)
    scores = {}
    for k in AES_KEYS:
        v = aes_n.get(k.replace("_", ""))
        if v is None:
            v = next((x for key, x in aes_n.items() if key.startswith(k.replace("_", "")[:6])), None)
        v = _num(v)
        scores[k] = (
            None if v is None else max(0.0, min(20.0, v)) * 5
        )  # reported on 0-100 per dimension, as in Code2Video Table 1
    sga = asker(SGA.format(material=text, **lesson))
    sga_n = _norm(sga)
    sga_scores = {}
    for k in SGA_KEYS:
        v = _num(sga_n.get(k.replace("_", "")))
        sga_scores[k] = None if v is None else max(0.0, min(100.0, v))
    return {
        "model": model,
        "run": run,
        "aes": scores,
        "aes_avg": _mean(scores.values()),
        "aes_notes": {
            "strengths": aes.get("strengths"),
            "improvements": aes.get("improvements"),
            **{
                k: (aes_n.get(k.replace("_", "")) or {}).get("feedback")
                if isinstance(aes_n.get(k.replace("_", "")), dict)
                else None
                for k in AES_KEYS
            },
        },
        "sga": sga_scores,
        "sga_avg": _mean(sga_scores.values()),
        "sga_notes": sga.get("notes"),
    }


def _num(v):
    if isinstance(v, dict):
        v = v.get("score")
    m = re.search(r"-?\d+(\.\d+)?", str(v)) if v is not None else None
    return float(m.group()) if m else None


def _mean(values):
    values = [v for v in values if v is not None]
    return round(float(np.mean(values)), 1) if values else None


# ── timing: what the picture does while the voice speaks ─────────────────────────────────────────────────────────
def timing(lesson, out, fps=2):
    folder = out / lesson["id"] / "fps2"
    if not folder.exists() or not any(folder.iterdir()):
        folder.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "ffmpeg",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(lesson["video"]),
                "-vf",
                f"fps={fps},scale=640:360",
                str(folder / "%05d.png"),
            ],
            check=True,
        )
    frames = [np.asarray(Image.open(f).convert("RGB")).astype(np.int16) for f in sorted(folder.glob("*.png"))]
    changed = [float((np.abs(b - a).sum(axis=2) > 60).mean()) for a, b in zip(frames, frames[1:], strict=False)]
    moving = np.array([c > 0.0002 for c in changed])  # same bar as pilot/khan/compare.py

    def moves(a, b):
        i, j = int(a * fps), max(int(a * fps) + 1, int(np.ceil(b * fps)))
        return bool(moving[i:j].any())

    cues = lesson["cues"]
    covered = [moves(a, b) for a, b, _ in cues]
    speech_bins = [(k / fps, (k + 1) / fps) for k in range(len(moving)) if any(a <= k / fps < b for a, b, _ in cues)]
    still_speech = [not moving[int(a * fps)] for a, _ in speech_bins]
    words = sum(len(t.split()) for _, _, t in cues)
    questions = sum(t.count("?") for _, _, t in cues)
    spoken = sum(b - a for a, b, _ in cues)
    longest = run = 0
    in_long_still = np.zeros(len(moving), bool)  # half-seconds inside a still stretch of 2 s or more
    for k, m in enumerate(moving):
        run = 0 if m else run + 1
        longest = max(longest, run)
        if run >= 2 * fps:
            in_long_still[k - run + 1 : k + 1] = True
    speech_still_2s = [bool(in_long_still[int(a * fps)]) for a, _ in speech_bins if int(a * fps) < len(in_long_still)]
    try:
        inter = (
            json.loads((lesson["root"] / "output" / "interactions.json").read_text(encoding="utf-8")).get(
                "interactions"
            )
            or []
        )
    except (OSError, ValueError):
        inter = []
    return {
        "duration_s": round(lesson["duration"], 1),
        "picture_change_share": round(float(moving.mean()), 3),
        "claims_covered": round(float(np.mean(covered)), 3) if covered else None,
        "speech_over_still": round(float(np.mean(still_speech)), 3) if still_speech else None,
        "speech_in_still_2s": round(float(np.mean(speech_still_2s)), 3) if speech_still_2s else None,
        "longest_still_s": round(longest / fps, 1),
        "words_per_minute": round(words / (spoken / 60), 1) if spoken else None,
        "questions_per_100_words": round(100 * questions / max(1, words), 2),
        "spoken_share": round(spoken / lesson["duration"], 3),
        "in_video_questions": len(inter),
    }


# ── the run ─────────────────────────────────────────────────────────────────────────────────────────────────────
CONDITIONS = ["none", "full", "voice", "pictures", "first12", "other", "know"]


def run_lesson(lesson_id, others, out, runs, steps, log):
    lesson = material(lesson_id, out)
    path = out / lesson_id / "result.json"
    result = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    result.update({"id": lesson_id, "topic": lesson["topic"], "grade": lesson["grade"], "language": lesson["language"]})
    if "timing" in steps:
        result["timing"] = timing(lesson, out)
    quiz = make_quiz(lesson, out) if {"quiz", "student"} & steps else None
    if quiz:
        result["quiz"] = {k: quiz[k] for k in ("written", "kept", "dropped")}
    if "student" in steps and quiz and quiz["questions"]:
        other = material(others[lesson_id], out)
        result["other_topic"] = other["topic"]
        trials = [(c, r, STUDENT) for c in CONDITIONS for r in range(1, runs + 1)]
        trials += [
            (c, r, STUDENT2) for c in ("none", "full", "know") for r in range(1, runs + 1)
        ]  # a second student, another family
        result["student"] = [student(lesson, quiz, c, r, other, m) for c, r, m in trials]
    if "evidence" in steps and result.get("student"):
        for s in result["student"]:
            if s["condition"] == "full" and s["model"] == STUDENT:
                evidence(lesson, quiz or make_quiz(lesson, out), s, out)
                if "claude" in steps:
                    try:
                        evidence(lesson, quiz or make_quiz(lesson, out), s, out, CLAUDE)
                    except RuntimeError as exc:
                        print(f"[baseline] {lesson_id}: Claude evidence skipped ({exc})")
    if "judge" in steps:
        result["judges"] = [judge(lesson, m, r) for m in JUDGES for r in range(1, min(runs, 2) + 1)]
        if "claude" in steps:
            try:
                result["judges"].append(judge(lesson, CLAUDE, 1))
            except RuntimeError as exc:
                print(f"[baseline] {lesson_id}: Claude judge skipped ({exc})")
    path.write_text(json.dumps(result, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    log(f"[baseline] {lesson_id} {lesson['topic'][:40]}: done")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "lessonforge_workspace" / "evals" / "study" / "baseline"))
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--lessons", default="")
    parser.add_argument("--steps", default="timing,quiz,student,evidence,judge,claude")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ids = [x for x in args.lessons.split(",") if x] or CORPUS
    rotation = random.Random(11).sample(CORPUS, len(CORPUS))
    others = {lid: rotation[(rotation.index(lid) + 7) % len(rotation)] if lid in rotation else CORPUS[0] for lid in ids}
    steps = set(args.steps.split(","))
    began = time.time()
    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_lesson, lid, others, out, args.runs, steps, print): lid for lid in ids}
        for f in cf.as_completed(futures):
            try:
                f.result()
            except Exception as exc:  # noqa: BLE001 - one lesson's failure is reported, the rest go on
                print(f"[baseline] {futures[f]} FAILED: {type(exc).__name__}: {exc}")
    print(f"[baseline] {len(ids)} lessons in {time.time() - began:.0f} s -> {out}")


if __name__ == "__main__":
    main()
