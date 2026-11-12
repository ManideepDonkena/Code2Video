# Results

## Pilot on MMMC (in progress)

12 topics, `bench/run_bench.py --n 12 --seed 0`, all models local. The tables are written by `bench/analyze.py`
into `bench/results/mmmc-n12-seed0/analysis.json` and copied here when the run finishes.

## First single-topic run (Pythagoras theorem, before the MMMC protocol): an anecdote

Class 8, 4 sections. TEST was half of our own filtered quiz (9 items); 3 student runs.

| Video | TEST: with video (3 runs) | TeachQuiz | Evidence-backed | First section only | MVQS |
|---|---|---|---|---|---|
| Base | 22, 22, 22 | +22.2 | 22.2 | 11.1 | 87.4 |
| Learner (s3 rewritten; s4's rewrite failed and the old one was kept) | 33, 33, 22 | +29.6 | 18.5 | 11.1 | 84.0 |
| Generic (s1 and s2 rewritten) | 22, 22, 22 | +22.2 | 22.2 | 11.1 | 85.0 |

Over the base video, `learner` gained 0.67 of a question on average out of 9, and `generic` gained nothing. One
topic, so this is not evidence.

## What the first runs taught (each is now handled in code)

| Problem seen | Effect | Fix |
|---|---|---|
| Unfiltered quizzes leak | the unlearned student scored 36% with no video; the first section alone beat the whole video | DEV item filter; a clean TEST score; S1 measured on other seeds |
| Asked for a list, a small judge copies the template's ids | every "yes" was lost: evidence 0% | one call per item (evidence and gap mapping) |
| A failed regeneration dropped its section | "revised" videos missing half their sections | the old code, layout record and clip are kept |
| Manim's rich traceback hides the line | block repair never ran | the failing line comes from partial execution |
| A model reply that is not JSON crashed the run | a lost run | a failed repair call stands aside |
| The local coder repeats API inventions (`get_side_length("BC")`, `.reverse()`, `Mobject(height=)`) | about a third of rewrites fail to render | a hint table; this is still the largest source of noise |
