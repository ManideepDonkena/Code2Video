# The lessonforge baseline (2026-11-12)

These scripts scored 21 finished lessonforge lessons with Code2Video's TeachQuiz and AES and with SGA's metrics. They read
lessonforge's lessons, so run them with lessonforge's virtualenv (`LESSONFORGE_ROOT` names the checkout,
default `/home/mani/manim/lessonforge`). The results are in `<lessonforge workspace>/evals/study/baseline-2026-11-12/`
and the write-up is the doc "Lessonforge vs Code2Video and SGA".

    $PY baseline/baseline.py --out <dir>                    # TeachQuiz, controls, evidence, AES/SGA judges, timing
    PYTHONPATH=<renderer copy with _scene_graph> $PY baseline/mvqs.py --out <dir>
    $PY baseline/summarize.py --baseline <dir> --mvqs <dir>

`mvqs.py` needs a copy of lessonforge's `longform/runtime.py` whose `still()` records a scene graph. That copy was in the
session scratchpad and is not kept here. The c2v-lab scene graph (`c2vlab/scene_graph.py`) does the same for any Manim scene.
