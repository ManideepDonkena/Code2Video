# c2v-lab

A small lab for code-to-video teaching research. It has no frontend, no server and no lesson pipeline: about 900 lines of Python
that do three things:

1. **Make** a short silent Manim video from a topic, the way Code2Video does (planner → coder → render, with escalating
   repair: block of lines, then the whole section).
2. **Check layout without rendering**, the way SGA does: run each section with `Scene.play` patched so animations
   jump to their end, record a scene graph (kind, box, variable name, creation line) after every play, score it with
   MVQS, and fix conflicts. The minimum separation vector is tried first as plain code (`name.shift(v)`), then given
   to the model for a ±5-line block, then for the whole section. A fix is kept only if MVQS goes up.
3. **Measure teaching and repair from it**: Code2Video's TeachQuiz with an unlearned student, plus controls (first
   section only, another topic's video), an evidence check (the moment the student cites must teach the answer),
   and **learner-feedback repair**, which is the idea under test.

## The idea under test, and whether it is new

**Idea:** the student's wrong answers on a DEV quiz are mapped to the section that should have taught them. Only those
sections are written again, with the missing idea. Success is measured on a held-out TEST quiz. The comparison is a
generic "teach it more clearly" revision of the same number of sections.

What the search found (2026-11-12). Each row was opened unless marked otherwise:

| Part of the idea | Already exists? | Where |
|---|---|---|
| Unlearned-student quiz as a **metric** for teaching videos | **Yes** | Code2Video (arXiv 2510.01174), TeachQuiz |
| Line → block → section escalating code repair | **Yes** | Code2Video ScopeRefine (`src/scope_refine.py`) |
| Scene graph from partial execution, MVQS, separation vector given to an LLM line patch | **Yes** | SGA (arXiv 2607.18116) |
| Simulated-learner outcome as the **reward to optimise** instructional material | **Yes, for text** | He-Yueya, Goodman, Brunskill (arXiv 2403.02795): LM-judged learning gains optimise math worksheets |
| Quiz linked to a generated STEM video; a wrong answer triggers new content | **Partly** | PIVOT (arXiv 2609.24083): a wrong answer makes a *new remediation video for that learner*. Quiz results do not revise the original video and are not traced to a segment |
| Visual self-correction of Manim code, learned or VLM-driven | **Yes** | ManimCode (arXiv 2611.08294), ManimAgent (arXiv 2606.30296). Their feedback is render and visual, not learner |
| Learner-perspective LLM judge | **Yes, evaluation only** | EduPanel (arXiv 2607.18529) |
| Simulated students to iterate quiz items | **Yes, for items** | VizQStudio (arXiv 2603.00994), not opened |
| **Unlearned-student failures, traced to a section by citation, repairing only that section of a code-generated video, scored on a held-out quiz against a generic-revision ablation** | **Not found** | — |

**Verdict:** each part already exists. Only the combination was not found: learner failures used as a localised
repair signal for code-generated video, with held-out evaluation and controls. The closest prior work is He-Yueya
et al. (the same principle, but for text worksheets) and PIVOT (quiz linked to video, but it remediates the learner,
not the video). The claim to make is "a localised learner signal beats a generic critic revision on held-out
learning gain". The generic-revision ablation exists to test exactly that, and the claim stands only if the ablation
loses.

The code-only shift (applying SGA's vector directly instead of asking a model) is a small engineering variation, not
a contribution.

## Models: theirs and ours

| Role | Code2Video | SGA | lessonforge (live) | c2v-lab default (local, free) |
|---|---|---|---|---|
| Planner / coder | GPT-4.1 in its run scripts; README: best code with Claude-4-Opus; GPT-5, GPT-4o, o4-mini, Gemini also selectable | GPT-5.1, GPT-5 mini, Claude 4.6 Sonnet, Gemini 3.0 Flash (the same model generates and repairs) | Claude Haiku 5.5 (script writer, scene code with thinking off) | `qwen3.6` (plan, quiz), `qwen3-coder:30b` (code) |
| Critic | Gemini 2.5 Pro (visual-anchor prompt) | Code2Video's critic as a baseline; its own repair is geometric | Gemini Flash frame review | none: scene graph + MVQS |
| TeachQuiz student | Gemini 2.5 Pro, watching the video | — | — (our baseline study: gemma4:26b) | `gemma4:26b` (forgets properly; qwen2.5vl:7b scored 87% before seeing anything) |
| Judge | Gemini 2.5 Pro (AES) | Gemini 3.0 Flash (VLM judge) | — (study: gemma4, qwen2.5vl, Claude Haiku 5.5) | `qwen2.5vl:7b` evidence judge |

The papers' models, as they appear on OpenRouter (checked 2026-11-12):

- `openai/gpt-4.1`
- `openai/gpt-5.1`
- `openai/gpt-5-mini` (must think)
- `anthropic/claude-opus-4.1`
- `anthropic/claude-sonnet-4.6`
- `google/gemini-2.5-pro` (must think)
- `google/gemini-3-flash-preview`

Any role can use one of them by prefixing `or:`:

```bash
C2V_CODER=or:openai/gpt-4.1 C2V_STUDENT=or:google/gemini-2.5-pro C2V_CAP_USD=2 python run.py all "Pythagoras theorem"
```

OpenRouter calls are written to `runs/ledger.jsonl` and are refused once `C2V_CAP_USD` (default 1.00) is spent. The key comes from `C2V_OPENROUTER_KEY`, or
`OPENROUTER_API_KEY`, or the `.env` file named by `C2V_ENV`. A key of its own for this study is best: lessonforge's
key has a cap that the app needs.

## Run

The lessonforge virtualenv already has Manim 0.20; any Python with `manim` and `numpy` works.

```bash
PY=/home/mani/manim/lessonforge/.venv/bin/python
$PY run.py all "Pythagoras theorem" --grade 8      # make, quiz, TEST TQ, learner round, generic round, TQ again
$PY run.py gen "Area of a triangle" --grade 7      # just make a video
$PY run.py layout runs/area-of-a-triangle          # scene graph + MVQS + repair for every section
$PY run.py quiz runs/area-of-a-triangle
$PY run.py eval runs/area-of-a-triangle --split test --other runs/pythagoras-theorem
$PY run.py feedback runs/area-of-a-triangle --mode learner   # or --mode generic
$PY -m c2vlab.scene_graph tests/overlap_scene.py S1 /tmp/g.json   # scene graph of any scene, about 1 s
```

## Files

| File | What it is |
|---|---|
| `c2vlab/llm.py` | `ask(model, prompt, images)` for Ollama or OpenRouter, with a JSON reply, a ledger and a cap |
| `c2vlab/generate.py` | plan, code per section, render, render-error repair (block → section), join |
| `c2vlab/scene_graph.py` | SGA partial execution: per-play resting states (kind, box, name, line) without rendering |
| `c2vlab/mvqs.py` | MVQS, conflicts, minimum separation vectors |
| `c2vlab/layout.py` | layout repair: shift (code) → block (model) → section (model); kept only if MVQS rises |
| `c2vlab/teachquiz.py` | quiz from the topic (DEV/TEST split), unlearned student, evidence check, controls |
| `c2vlab/feedback.py` | learner-feedback round and the generic ablation |
| `run.py` | command line |

## Known limits

- The student sees 3 frames per section, not the video, so motion is not judged. Code2Video's student watched the
  video.
- Videos are silent. `material(..., narration=True)` adds the planned narration as text. Our baseline found that the
  voice alone taught as much as the full video.
- One topic run is an anecdote. Run spread was up to 30 points in our baseline. A claim needs many topics (e.g.
  MMMC's 117) and several student seeds.
- MVQS formulas follow SGA's listed weights. Where SGA gives no formula (severity weights, separation, labelling),
  this repo makes its own choice, and the docstring says which.
