# Pipeline ablation: novel12

Metric: M9 (gain on 3 frames per section, continuous, two option orders).

| Stage | Features | learner − base | learner − generic | learner − learner_all | generic − base |
|---|---|---|---|---|---|
| F0 | pilot loop | +0.061 [-0.087, +0.208] 6/0/4, p 0.4922 | +0.061 [-0.087, +0.193] 6/0/4, p 0.4922 | +0.096 [-0.033, +0.221] 6/0/4, p 0.1934 | -0.000 [-0.098, +0.095] 6/0/4, p 0.9219 |
| F1 | gate | +0.077 [+0.002, +0.174] 4/5/1, p 0.125 | +0.056 [-0.018, +0.157] 4/1/5, p 0.7344 | +0.049 [-0.038, +0.151] 3/5/2, p 0.4375 | +0.021 [-0.050, +0.087] 5/3/2, p 0.375 |

Metric: M7 (D-VGAIN on the dense video, continuous, two option orders).

| Stage | Features | learner − base | learner − generic | learner − learner_all | generic − base |
|---|---|---|---|---|---|
| F0 | pilot loop | -0.005 [-0.176, +0.127] 6/0/4, p 0.5566 | +0.034 [-0.133, +0.172] 7/0/3, p 0.375 | -0.014 [-0.089, +0.050] 7/0/3, p 0.9219 | -0.039 [-0.146, +0.040] 5/0/5, p 0.8457 |
| F1 | gate | -0.037 [-0.186, +0.062] 3/5/2, p 0.8125 | -0.037 [-0.167, +0.051] 4/1/5, p 1.0 | -0.021 [-0.088, +0.037] 3/5/2, p 0.8125 | +0.000 [-0.029, +0.028] 4/3/3, p 0.9375 |

| Stage | sections asked (learner) | rewritten and rendered | served revisions (of topics) | mean edit size | MVQS learner | sections learner |
|---|---|---|---|---|---|---|
| F0 | 32 | 25 | 10/10 | None | 81.271 | 4 |
| F1 | 32 | 25 | 5/10 | None | 84.476 | 4 |
