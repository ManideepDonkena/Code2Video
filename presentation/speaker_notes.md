# TeachCheck: speaker notes for the project meeting

Deck: https://claude.ai/artifact/SXQdfpwa89Nh7VC5n12Jqi
Slot: 17 November, 19:30. Group 18. Aim for about 10 minutes on slides 1 to 20, then the code.

**If you have only one minute:** We tried to repair generated teaching videos where a simulated student fails. The
pilot showed nothing, and the audit showed that the standard measure could not have shown anything. So we built a
measure that subtracts what the student already knows, and a benchmark of invented concepts. On those, the videos
teach, but neither cleaner layout nor our repair loop gave a gain beyond noise.

---

## 1. Title
We are Group 18. Our project starts from Code2Video. The question is in the title: does a generated teaching video
actually teach?

## 2. Models can now write maths lessons as code
A planner writes a lesson plan, a coder writes one Manim scene per section, and a renderer makes the video. A video
can look clean and still teach nothing. People are too slow to test every version, so the field uses a simulated
student: a vision-language model that looks at frames and takes a quiz.

## 3. We repair the video where the student fails
Our idea: if the student's quiz can test a video, its mistakes can show where the video is weak. The student takes a
practice quiz, we trace each wrong answer to a section, and the coder rewrites only that section. The claim is narrow:
this must beat an equal rewrite made without the student's feedback, on questions nobody has seen.

## 4. The study ran in four steps
Step 0 is the pilot and the audit. Step 1 rebuilds the measure on MMMC. Step 2 moves to invented concepts and also
checks video quality. Step 3 adds five features to the repair loop. Each step exists because of what the one before
found.

## 5. TeachQuiz tells the student to forget
TeachQuiz is Code2Video's measure. The model is told to forget the topic and to answer NULL when the video does not
show the answer. The score is the quiz with the video minus the quiz without it. It assumes the model really forgets.
Nobody had checked that.

## 6. The pilot on 12 topics showed no effect
Twelve MMMC topics. Our repair is one or two points above the base video, and 7 of 12 topics are exact ties, most at
zero. Also, the diagnosis called 124 of 127 practice questions gaps, so "fix the weak section" became "fix almost
everything". We asked why.

## 7. The audit found three breaks in the measure
First, a grading bug: the student copied the id q1 from the answer template, the questions are named t1 to t5, and
52% of graded runs were lost. Second, refusal: told to forget, it answers NULL on 100% of items without the video and
85% with it. It refuses; it does not forget. Third, it already knows the answers.

## 8. 99%
This is the number to remember. We removed NULL, showed the student nothing, and it answered 99% of MMMC correctly.
Smaller models do the same: 97.4% and 91.9%. No video can show a gain on questions the student already knows.

## 9. D-VGAIN subtracts what the student knew
Our measure. The student must choose, so refusing cannot pass as not knowing. We measure what it knew with no video
and report the gain over that. And we compare the moving video with its start and end frames, to see what motion
adds. We read the probability on each letter, over two option orders.

## 10. On MMMC the student leaves no room to learn
We add the parts one at a time, M0 to M9, and test each version the same way. On all 12 pilot topics the student is
already right on every question, so every gain measure is undefined. We report undefined, never zero. So the pilot's
null result says nothing against the repair.

## 11. NOVEL-12 uses concepts no model has seen
We invented twelve small maths concepts, each on one card. 96 questions, written by Claude, which the pipeline never
uses, with numeric answers computed by code. Without the video the student scores 41.1%, near chance. With the card
as text it scores 84.9%. So there is room to learn.

## 12. On invented concepts the videos teach
The gain on 3 frames per section is +42.4 points, positive on 9 of 10 concepts. A concept's own video beats another
concept's video by +64.4 points, on 10 of 10. Both are beyond noise, and Claude Haiku and Sonnet as students agree.
Three frames beat the dense video mostly because the frames are larger.

## 13. An admission check keeps only complete videos
7 of 12 base videos had silently dropped a section that failed to render. After one retry, 10 are complete and enter
the study; 5 are also clean. Two stayed incomplete and are excluded. That is a limit of the local coder.

## 14. The layout score misses faults a viewer sees
Claude fixed 96 visible faults in 40 sections. Conflicts fell from 31 to 4 and broken attachments from 13 to 4, but
the layout score moved only from 84.2 to 85.6. In this example the score fell 21 points when the fix was right,
because the score measures distance between boxes. Our own repair had caused it.
(If asked: with a later tracker fix the conflict counts are 27 and 4; nothing else changes.)

## 15. Cleaner layout did not clearly teach more
We fixed the rule before scoring: at least 5 points on average and at least 7 of 10 concepts. We got +5.1 but only 5
of 10, so the rule is not passed. One concept carries the mean. The study can only detect effects of about 24
points, so this is a weak null result, not proof of no effect.

## 16. We added five repair features one at a time
F0 is the pilot loop. F1 enforces the gate. F2 checks the code before rendering. F3 finds the weak section like a
debugger, with an Ochiai score. F4 stops a fix from copying the practice question. F5 makes minimal edits.

## 17. No repair stage gave a gain beyond noise
The lead of the learner repair over a generic repair stays between +2.0 and +6.3 points. The gate kept the learner
revision on only 1 to 5 of 10 concepts, so no difference could hold across concepts. Two features did their job: the
code check and the minimal edits.

## 18. The study gives five findings
Read the five lines. Stress the first two as the contribution: the audit of TeachQuiz, and a measure and benchmark
where learning can be seen. The last three are honest negative results.

## 19. The study is small; four next steps follow
Ten concepts, one main student that sees frames, questions from one model. Next: more concepts, a gate that counts
layout faults, stronger coders with an anchor grid, and students that watch the video with audio.

## 20. Thank you
What we built: D-VGAIN and the ladder, NOVEL-12, the video checks, and six repair stages. Everything is in the
showcase repository.

---

## Likely questions

- **Why trust the new measure?** A concept's own video beats another concept's video on 10 of 10 concepts. TeachQuiz
  after the grading fix also separates them, but it cannot separate a repair from its base video.
- **Is the null result real?** It is a weak null. With 10 concepts of 8 questions, only effects of about 24 points
  can be detected. Small gains remain possible.
- **Why invented concepts?** Because the student knows 99% of MMMC. The idea comes from TOFU's invented authors.
- **Why did the gate reject so much?** It needs the practice score not to fall and the layout score to fall by less
  than 5 points. Most revisions failed one of the two.
- **What did Claude do?** It wrote the NOVEL-12 questions, made the reference layout fixes, and served as two extra
  students. It is not part of the pipeline. Total API cost was about 7 dollars.
- **Repeatability?** The student is not fully repeatable at temperature 0: 33 of 232 repeated questions moved. The
  noise model accounts for this.

## Code walkthrough

Use `presentation/code_walkthrough.md`. Open the files in pipeline order: `pipeline.py`, `generate.py`,
`preflight.py`, `scene_graph.py`, `mvqs.py`, `layout.py`, `attach.py`, `temporal.py`, `dvgain.py`, `feedback.py`,
`stages.py`. Three functions are worth showing on screen: `dvgain.nvg`, `stages.ochiai` and `layout.shift_patch`.
