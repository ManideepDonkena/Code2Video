# TeachCheck: code walkthrough of the showcase repository

Repository: `github.com/ManideepDonkena/c2v-showcase`. All paths below are under its `code/` folder.
The core package is `c2vlab/` (about 3,200 lines). The studies are in `bench/` (about 3,000 lines).

Follow the files in this order. It is the order in which a topic moves through the system.

| Step | Files | What happens |
|---|---|---|
| 1. Make the video | `c2vlab/generate.py`, `pipeline.py`, `llm.py` | Topic, plan, one Manim scene per section, render, join |
| 2. Check the code | `c2vlab/preflight.py`, `admission.py` | Static checks before a render; the admission check |
| 3. Check the layout | `c2vlab/scene_graph.py`, `mvqs.py`, `layout.py` | Scene graph without rendering, layout score, layout repair |
| 4. Model-free checks | `c2vlab/attach.py`, `temporal.py` | Broken attachments; text left on screen |
| 5. Measure teaching | `c2vlab/teachquiz.py`, `dvgain.py` | TeachQuiz, the forced-choice probe, D-VGAIN, M0 to M9 |
| 6. Repair | `c2vlab/feedback.py`, `stages.py` | The pilot loop (F0) and the stages F1 to F5 |
| 7. Studies | `bench/*.py`, `bench/novel/` | Benchmark runs, metric ladder, stage study, noise model, NOVEL-12 |
| 8. Paper numbers | `paper/make_tables.py` | Every table and number, from the result files |

Entry point: `run.py` (one topic at a time). `bench/run_bench.py` runs many topics.

---

## 1. Making the video

**`c2vlab/llm.py`** is the only place that calls a model.

- `ask()` (line 311) sends a prompt and returns JSON. A model name is an Ollama model (`gemma4:26b`), an
  OpenRouter id (`or:...`) or a Claude id (`claude:...`).
- `ask_logprobs()` (line 284) returns a local reply at temperature 0 with the top log-probabilities of every token.
  The measure in step 5 is built on this call.
- The roles are set here: `PLANNER = qwen3.6:latest`, `CODER = qwen3-coder:30b`, `STUDENT = gemma4:26b`,
  `JUDGE = qwen2.5vl:7b`. Paid calls are written to a ledger and refused past a cost cap.

**`c2vlab/generate.py`** turns a topic into section videos.

- `plan()` (line 214): the planner writes the sections. Each has what it teaches, what it shows and its narration.
  For an invented concept the prompt also carries the concept's card (`SOURCE`).
- `write_code()` (line 252): the coder writes one Manim scene per section, as `sections/sN.py`.
- `render()` (line 274): renders one section at low quality and returns the mp4 or the error text.
- `build_section()` (line 330): write, render, and on failure repair. The repair widens in steps, as in Code2Video's
  ScopeRefine: the failing line, then a block (`patch_block`, line 302), then the whole section (`rewrite`, line 319).
  At most 4 tries. `HINTS` maps common Manim errors to a short hint for the coder.
- `join()` (line 406): joins the clips into `video.mp4` and writes `sections.json` with each section's start and end.

**`c2vlab/pipeline.py`** ties one topic together.

```python
def make_video(topic, grade, out, sections=4, log=print, source=None):
    p = generate.plan(topic, grade, sections, out, source=source)
    clips = {}
    for s in p["sections"]:
        if generate.build_section(p, s, out, log):
            layout.repair(s["id"], out, log=log)
            mp4, _ = generate.render(out / "sections" / f"{s['id']}.py", s["id"].upper(), out / "media")
            if mp4:
                clips[s["id"]] = mp4
    generate.join(out, p, clips)
    return out
```

`run_topic()` then writes the quizzes, evaluates the base video and runs one repair per mode (`learner`, `generic`,
`learner_all`). Every step writes its file under `runs/<topic>/` and is skipped when that file exists, so a run
can be restarted.

---

## 2. Checking the code before rendering

**`c2vlab/preflight.py`** (stage F2). `check()` (line 62) reads the code without running it. Each check matches a
failure class seen in the pilot:

| Check | What it catches |
|---|---|
| `syntax` | the code does not parse |
| `name` | a name defined nowhere (not in Manim, builtins or the code) |
| `kwarg` | a keyword that a Manim class's constructor chain does not accept (read with `inspect.signature`) |
| `method` | a method that no Manim class, numpy array or container has |
| `asset` | an external file or URL |

A check that cannot decide stays silent, because a false alarm costs a repair that was not needed.
`safe_splice()` (line 120) replaces lines only if the result still parses. In the pilot, 38 failed attempts were
syntax errors that our own patch had introduced.

**`c2vlab/admission.py`**. `admit()` (line 85) checks one base video against three targets: every planned section
renders; every section has MVQS of at least 70 (`MIN_MVQS`) with no lasting conflict; and a person approves a contact
sheet (`bench/admit.py` writes it). A failing section is written again once (`TRIES = 1`) and the better attempt is kept.

---

## 3. Checking the layout without rendering

**`c2vlab/scene_graph.py`**. `run()` (line 63) executes the section's `construct()` with `Scene.play` patched, so every
animation jumps to its end and nothing is drawn. After each play it records every visible object:

- `kind`: Text, Geom, Mark or Deco
- `box`: `[x0, y0, x1, y1]` in scene units (the frame is 14.22 by 8)
- `name`: the variable in `construct()` that holds it
- `line`: the line of the section's file where it was created

A scene runs in about a second. An exception stops the run but keeps the states recorded so far.

**`c2vlab/mvqs.py`** scores those states. `mvqs()` (line 124) uses SGA's weights:

```
MVQS = 0.5 * S_sp + 0.2 * S_ly + 0.3 * S_ed
S_sp = overlap, inside the frame, legible, separation
S_ly = density, distribution over a 4x3 grid
S_ed = labelling, states with no persistent conflict
```

`conflicts()` (line 49) finds text overlaps and gives each a minimum separation vector
(`separation_vector`, line 28). `persistent_conflicts()` (line 175) keeps the ones a viewer sees at rest.
`crowding()` (line 146) finds two texts nearer than 0.15 units, or a text wider than the frame.

**`c2vlab/layout.py`**. `repair()` (line 112) tries three levels, and keeps a try only if it runs and is better:

1. `shift` (no model): insert `name.shift(v)` before the play where the conflict appears.
2. `block` (model): the lines around the object's creation, with the conflict and the vector named.
3. `section` (model): the whole scene again.

```python
def shift_patch(code, c):
    name, line = c["move"].get("name"), c.get("after_line")
    ...
    dx, dy = c["vector"]
    rows.insert(line - 1, f"{indent}{name}.shift({dx} * RIGHT + {dy} * UP)  # layout: separation vector")
    new = "\n".join(rows) + "\n"
    try:
        ast.parse(new)
    except SyntaxError:
        return None
    return new
```

This shift is the cause of the *Glint numbers* example in the paper: it moved the highlight boxes off their digits
and the score went up. Our repair added 41 such shifts and Claude removed 38.

---

## 4. The two model-free checks

**`c2vlab/attach.py`** asks whether each label, arrow or box still sits at the object the code attached it to.
`relations()` (line 41) reads the attachments from the code. `broken()` (line 93) compares them with the scene graph.

| Code | Meaning | Broken when |
|---|---|---|
| `X.next_to(Y, ...)` | X belongs beside Y | the gap exceeds `NEAR = 1.0` |
| `X.move_to(Y)` | X belongs on Y | the gap exceeds `ON = 0.5` |
| `Arrow(Y.get_*(), Z.get_*())` | the arrow ends at Y and Z | the gap to either exceeds `NEAR` |

A pair is judged in the last state in which both are on screen. Labels anchored to a text glyph are skipped.

**`c2vlab/temporal.py`** finds faults of when things are on screen. `check()` (line 59) reads the code only.

- `residue`: `Transform(a, b)` leaves `a` on screen, so a later `FadeOut(b)` does nothing. The fix is
  `ReplacementTransform(a, b)`.
- `prose_math`: a sentence given to `MathTex` loses its spaces. The fix is `Text(...)`.
- `never_shown`: an object is built but never added.

`fix()` (line 110) applies the first two, and keeps a fix only if the code still parses.

---

## 5. Measuring teaching

**`c2vlab/teachquiz.py`** is Code2Video's TeachQuiz, with the grading fix.

- `make_quiz()` (line 95) writes DEV (from our planner; the repair may see it) and takes TEST (MMMC's official
  questions, or NOVEL-12's; no step sees it).
- `material()` (line 154) takes 3 frames per section, at 40, 70 and 95% of it (`SHARES`).
- `grade_reply()` (line 196) is version M1. It matches answers by id, and by order when no id matches:

```python
answers = [a for a in reply.get("answers") or [] if isinstance(a, dict)]
got = {a.get("id"): a for a in answers}
by_order = not any(q["id"] in got for q in questions) and len(answers) == len(questions)
```

The template's example id is `q1`. The student copied it for TEST questions named `t1..t5`, and 52% of graded runs
were lost when matched by id only.

**`c2vlab/dvgain.py`** is the new measure.

- `material()` (line 84) builds the four materials: nothing, 3 frames per section, the first and last frame of each
  section, and the dense silent video at `FPS = 4` (at most `MAX_FRAMES`, so the prompt fits a 32k context).
- `probe()` (line 137) makes one call per material and option order. The student answers every question in one
  reply, one line each (`1: B`).
- `parse()` (line 115) reads the probabilities of A to D at each answer position.
- `rotate()` (line 96) shifts the options; `ROTATIONS = (0, 1)` gives two orders.
- `score()` (line 188) averages right or wrong, or P(right), over items and orders.

```python
def nvg(s, s_blind):
    b = max(CHANCE, s_blind)
    return None if 1 - b < MIN_ROOM else (s - b) / (1 - b)

def dvgain(s_visual, s_static, s_blind):
    n = nvg(s_visual, s_blind)
    return None if n is None else n + LAMBDA * max(0.0, s_visual - s_static)
```

`CHANCE = 0.25`, `LAMBDA = 0.5`, `MIN_ROOM = 0.05`. When the student already knows the answers, `nvg` returns
`None`, which the tables print as undefined. This is why M3 to M9 score 0 of 12 videos on MMMC.

`bench/metric_ladder.py` computes every version M0 to M9 from the same cached probes and applies the four tests
(scored, own minus other, agreement, ties).

---

## 6. The repair loop

**`c2vlab/feedback.py`** is the pilot loop, stage F0.

1. `diagnose()` (line 150): the student answers DEV with the video. `gaps()` (line 52) lists the questions it never
   got right with accepted evidence. `plan_fixes()` (line 69) asks the planner, one call per gap, which section
   should have taught it and what idea was missing. An idea that copies six words of the question is refused.
2. `revise()` (line 95): only the named sections are written again. A section that fails to render keeps its old
   version.
3. `round_()` (line 165): the gate.

```python
kept = (bool(changed) and after["teachquiz"] >= before["teachquiz"] and (m0 is None or m1 is None or m1 > m0 - 5)
        and (f0 is None or f1 <= f0))
```

The three modes share the diagnosis: `learner` rewrites the diagnosed sections, `generic` rewrites as many sections
chosen at random with "teach this more clearly", and `learner_all` rewrites every section.

**`c2vlab/stages.py`** adds one feature per stage, as a set of switches:

```python
FEATURES = {
    "F0": set(), "F1": {"gate"}, "F2": {"gate", "preflight", "safe_patch"},
    "F3": {"gate", "preflight", "safe_patch", "sbfl"}, "F4": {"gate", "preflight", "safe_patch", "sbfl", "leak_gate"},
    "F5": {"gate", "preflight", "safe_patch", "sbfl", "leak_gate", "minimal_edit"},
}
```

- **F1, gate enforced**: a revision that fails the gate is not used; TEST sees the base video.
- **F2, code reliability**: `preflight.check` before every render, `safe_splice`, and `temporal.fix`.
- **F3, localisation**: `dev_items()` (line 81) scores each DEV question by P(right). `qmatrix()` (line 96) maps
  every question to one section. `ochiai()` (line 113) ranks the sections:

```python
def ochiai(items, qmap, sections):
    failing = {i for i, p in items.items() if p < PASS}
    total_f = len(failing)
    rank = {}
    for s in sections:
        ef = sum(1 for i in failing if qmap.get(i) == s)
        ep = sum(1 for i in items if i not in failing and qmap.get(i) == s)
        rank[s] = ef / math.sqrt(total_f * (ef + ep)) if ef else 0.0
    return rank, failing
```

  `PASS = 0.5`. Only the top section is repaired (the top two when there are more than three sections).
- **F4, leak gate**: `leaks()` (line 124) refuses an idea that repeats two or more numbers of its DEV question, or
  one of its options. The ideas of a section are merged into one general principle (`MERGE`).
- **F5, minimal edits**: `edit_code()` (line 196) asks the coder to change the working scene as little as possible.
  `revise()` (line 204) records the size of every edit.

`round_()` (line 253) runs one stage for one base video in one mode and caches its report.

---

## 7. The studies and the paper's numbers

| Script | What it produces |
|---|---|
| `bench/run_bench.py` | Base videos and the F0 repairs for a set of topics |
| `bench/mmmc_prior.py` | What the student already knows on MMMC (the 99%) |
| `bench/novel/build.py` | NOVEL-12 cards and TEST questions; numeric answers computed by code |
| `bench/metric_ladder.py` | The ladder M0 to M9 on a results folder |
| `bench/admit.py` | The admission check and the contact sheets |
| `bench/claude_fix.py`, `layout_study.py` | The Claude-fixed reference videos and the layout study |
| `bench/shift_attach.py`, `repair_layout.py` | Whether shifts break attachments; layout of the kept repairs |
| `bench/stages.py` | The stage study F1 to F5 |
| `bench/claude_student.py` | Claude Haiku and Sonnet as students |
| `bench/noise_model.py` | Which differences are beyond noise |
| `paper/make_tables.py` | Every table and macro in `paper/tables/` |

## 8. Running it

```bash
python run.py topic "Pythagoras theorem"            # one topic: video, quiz, evaluation, every repair mode
python bench/novel/build.py                         # NOVEL-12 cards and questions
python bench/run_bench.py --name novel12 --n 10 --questions bench/novel/questions_admitted.json \
    --cards bench/novel/cards.json                  # NOVEL-12 base videos (F0)
python bench/metric_ladder.py bench/results/novel12 # the metric ladder
python bench/stages.py bench/results/novel12 --stage F1   # one repair stage; F1 to F5
python bench/noise_model.py                         # the noise model
python bench/layout_study.py                        # the layout study
python paper/make_tables.py                         # every table and number (needs no model)
```

`code/REPRODUCE.md` lists the exact model builds. Two cautions from it: the student is not fully repeatable at
temperature 0, and the registry now serves a newer `gemma4:26b` build, so a fresh run will not match the paper's
numbers exactly.
