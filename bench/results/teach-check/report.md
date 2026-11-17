# Teach check: delivery and coverage

Delivery: can the student read what this video shows (questions about the video's own content)? Coverage: does the video show what each final-quiz question needs (a judge that may know the topic)? Both on 3 frames per section, 0-100. See c2vlab/delivery.py.

| Set | Videos | Delivery | Coverage | M9 | Layout score | Delivery questions kept (of written) |
|---|---|---|---|---|---|---|
| Local models, base | 10 | 71.6 | 82.5 | 42.4 | 84.2 | 7.3 (15.2) |
| Local + Claude layout fix | 10 | 79.2 | 88.8 | 47.6 | 85.6 | 7.3 (15.2) |
| Claude Sonnet 5.5 | 10 | 85.5 | 87.5 | 64.1 | 86.4 | 7.9 (15.8) |
| Claude Opus 5.5 | 5 | 84.8 | 95.0 | 76.5 | 88.5 | 9.4 (16.0) |

## Controls: the same questions on another topic's video

| Set | Delivery own | Delivery other | own > other | Coverage own | Coverage other | own > other |
|---|---|---|---|---|---|---|
| Local models, base | 71.6 | -15.0 | 10/10 (p 0.002) | 82.5 | 26.2 | 8/10 (p 0.0391) |

## Do they move with M9? (NOVEL-12 videos; Spearman, permutation p)

| Pair | n | rho | p |
|---|---|---|---|
| delivery vs m9 all | 35 | 0.295 | 0.0844 |
| coverage vs m9 all | 35 | -0.032 | 0.8597 |
| mvqs vs m9 all | 35 | 0.365 | 0.0347 |
| delivery vs m9 within concept | 35 | 0.388 | 0.0227 |
| coverage vs m9 within concept | 35 | 0.054 | 0.7614 |
| mvqs vs m9 within concept | 35 | 0.241 | 0.1666 |
| delivery vs m9 local | 10 | 0.636 | 0.0541 |
| coverage vs m9 local | 10 | -0.108 | 0.7695 |
| delivery vs coverage all | 35 | -0.032 | 0.8516 |

## Coverage, question by question

Covered questions (245): the frames raise P(right) by +35.5 points. Not covered (35): +15.4. Difference +20.0 (labels shuffled inside each video: p 0.0228).

## Layout fix (same text): Claude-fixed minus local

Delivery +7.6 (6/2/2, p 0.2891); M9 +5.1 (5/0/5); layout score +1.4.

## Blueprint prompt minus plain prompt (same plans, local coder)

- delivery: -- (0/0/0, sign-test p 1.0)
- coverage: -- (0/0/0, sign-test p 1.0)
- m9: -- (0/0/0, sign-test p 1.0)

## Every video

| Set | Topic | Sections | Delivery | on other | Questions | Coverage | on other | M9 |
|---|---|---|---|---|---|---|---|---|
| local | Tovan sums | 4/4 | 85.3 | -11.7 | 6 | 100.0 | 0.0 | 76.4 |
| claude_layout | Tovan sums | 4/4 | 74.4 | -- | 6 | 87.5 | -- | 65.5 |
| local | Krell steps on a grid | 4/4 | 36.7 | -8.2 | 10 | 75.0 | 0.0 | 25.8 |
| claude_layout | Krell steps on a grid | 4/4 | 69.2 | -- | 10 | 100.0 | -- | 50.0 |
| local | Vorn sequences | 4/4 | 100.0 | -6.7 | 7 | 100.0 | 12.5 | 42.7 |
| claude_layout | Vorn sequences | 4/4 | 100.0 | -- | 7 | 100.0 | -- | 39.6 |
| local | Glint numbers | 4/4 | 74.9 | -43.8 | 6 | 87.5 | 0.0 | 79.2 |
| claude_layout | Glint numbers | 4/4 | 83.7 | -- | 6 | 62.5 | -- | 71.2 |
| local | Mirthful triangles | 4/4 | 69.0 | -12.7 | 11 | 37.5 | 100.0 | 42.0 |
| claude_layout | Mirthful triangles | 4/4 | 75.3 | -- | 11 | 87.5 | -- | 16.2 |
| local | Sorrel counts of lattice rectangles | 4/4 | 53.0 | 3.5 | 4 | 100.0 | 0.0 | -27.9 |
| claude_layout | Sorrel counts of lattice rectangles | 4/4 | 83.4 | -- | 4 | 100.0 | -- | 34.8 |
| local | Quill distance | 4/4 | 72.4 | -1.2 | 9 | 100.0 | 100.0 | 26.9 |
| claude_layout | Quill distance | 4/4 | 80.5 | -- | 9 | 100.0 | -- | 36.0 |
| local | Dapple numbers | 4/4 | 60.6 | -27.4 | 8 | 87.5 | 0.0 | 45.6 |
| claude_layout | Dapple numbers | 4/4 | 68.1 | -- | 8 | 87.5 | -- | 48.5 |
| local | Orbit words | 4/4 | 100.0 | -7.9 | 4 | 50.0 | 37.5 | 61.9 |
| claude_layout | Orbit words | 4/4 | 100.0 | -- | 4 | 62.5 | -- | 65.0 |
| local | Vells of 2×2 grids | 4/4 | 63.6 | -34.0 | 8 | 87.5 | 12.5 | 51.8 |
| claude_layout | Vells of 2×2 grids | 4/4 | 57.3 | -- | 8 | 100.0 | -- | 49.1 |
| sonnet | Tovan sums | 4/4 | 99.5 | -- | 8 | 100.0 | -- | 82.5 |
| sonnet | Vorn sequences | 4/4 | 100.0 | -- | 3 | 100.0 | -- | 99.0 |
| sonnet | Mirthful triangles | 4/4 | 73.3 | -- | 10 | 75.0 | -- | 42.6 |
| sonnet | Glint numbers | 4/4 | 76.8 | -- | 8 | 75.0 | -- | 99.5 |
| sonnet | Krell steps on a grid | 4/4 | 87.9 | -- | 8 | 100.0 | -- | 61.2 |
| sonnet | Sorrel counts of lattice rectangles | 4/4 | 92.3 | -- | 9 | 75.0 | -- | 18.3 |
| sonnet | Quill distance | 4/4 | 100.0 | -- | 7 | 100.0 | -- | 42.6 |
| sonnet | Vells of 2×2 grids | 4/4 | 33.8 | -- | 8 | 100.0 | -- | 46.4 |
| sonnet | Orbit words | 4/4 | 91.4 | -- | 8 | 75.0 | -- | 75.7 |
| sonnet | Dapple numbers | 4/4 | 100.0 | -- | 10 | 75.0 | -- | 73.4 |
| opus | Vorn sequences | 4/4 | 100.0 | -- | 9 | 100.0 | -- | 96.5 |
| opus | Tovan sums | 4/4 | 70.8 | -- | 10 | 100.0 | -- | 99.7 |
| opus | Krell steps on a grid | 4/4 | 77.5 | -- | 7 | 100.0 | -- | 74.9 |
| opus | Glint numbers | 4/4 | 86.0 | -- | 10 | 75.0 | -- | 66.8 |
| opus | Quill distance | 4/4 | 89.9 | -- | 11 | 100.0 | -- | 44.6 |
