# Pipeline ablation: novel12

Metric: M9 (gain on 3 frames per section, continuous, two option orders).

| Stage | Features | learner − base | learner − generic | learner − learner_all | generic − base |
|---|---|---|---|---|---|
| F0 | pilot loop | +0.061 [-0.087, +0.208] 6/0/4, p 0.4922 | +0.061 [-0.087, +0.193] 6/0/4, p 0.4922 | +0.096 [-0.033, +0.221] 6/0/4, p 0.1934 | -0.000 [-0.098, +0.095] 6/0/4, p 0.9219 |
| F1 | gate | +0.077 [+0.002, +0.174] 4/5/1, p 0.125 | +0.056 [-0.018, +0.157] 4/1/5, p 0.7344 | +0.049 [-0.038, +0.151] 3/5/2, p 0.4375 | +0.021 [-0.050, +0.087] 5/3/2, p 0.375 |
| F2 | gate, preflight, safe_patch | +0.122 [+0.011, +0.267] 4/6/0, p 0.125 | +0.034 [-0.013, +0.097] 4/4/2, p 0.4375 | +0.125 [+0.000, +0.307] 3/6/1, p 0.25 | +0.088 [+0.015, +0.199] 5/4/1, p 0.0625 |

Metric: M7 (D-VGAIN on the dense video, continuous, two option orders).

| Stage | Features | learner − base | learner − generic | learner − learner_all | generic − base |
|---|---|---|---|---|---|
| F0 | pilot loop | -0.005 [-0.176, +0.127] 6/0/4, p 0.5566 | +0.034 [-0.133, +0.172] 7/0/3, p 0.375 | -0.014 [-0.089, +0.050] 7/0/3, p 0.9219 | -0.039 [-0.146, +0.040] 5/0/5, p 0.8457 |
| F1 | gate | -0.037 [-0.186, +0.062] 3/5/2, p 0.8125 | -0.037 [-0.167, +0.051] 4/1/5, p 1.0 | -0.021 [-0.088, +0.037] 3/5/2, p 0.8125 | +0.000 [-0.029, +0.028] 4/3/3, p 0.9375 |
| F2 | gate, preflight, safe_patch | -0.112 [-0.262, +0.000] 1/6/3, p 0.25 | -0.054 [-0.122, +0.004] 2/4/4, p 0.2188 | -0.039 [-0.109, +0.001] 2/6/2, p 0.625 | -0.058 [-0.151, +0.009] 2/4/4, p 0.3125 |

| Stage | sections asked (learner) | rewritten and rendered | served revisions (of topics) | mean edit size | MVQS learner | sections learner |
|---|---|---|---|---|---|---|
| F0 | 32 | 25 | 10/10 | None | 81.271 | 4 |
| F1 | 32 | 25 | 5/10 | None | 84.476 | 4 |
| F2 | 32 | 28 | 4/10 | 0.691 | 84.244 | 4 |
