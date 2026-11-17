# Blueprint layout prompt against the plain prompt (local coder, 10 concepts, same plans)

| | Blueprint | Plain |
|---|---|---|
| Sections rendered on the first try | 38 | 38 |
| Sections clean on the first try | 27 | 24 |
| Sections in the final video | 39 | 40 |
| Videos clean after admission | 7 | 4 |
| Lasting conflicts | 8 | 13 |
| Timing faults | 0 | 0 |
| Broken attachments | 2 | 9 |
| Rule: layout comment | 39 | 0 |
| Rule: fit calls | 338 | 0 |
| Rule: move to xyz | 262 | 2 |
| Rule: arrange | 19 | 6 |
| Rule: to edge or corner | 0 | 64 |
| Rule: move to origin | 0 | 20 |
| Rule: unit size | 0 | 1 |
| Rule: texts | 248 | 166 |
| Rule: long texts | 27 | 38 |
| Layout score (MVQS) | 85.2 | 84.7 |
| M9 | 56.8 | 45.0 |
| Confidence with 3 frames | 73.8 | 68.2 |

Paired differences (blueprint minus plain):

- Layout score (MVQS): {"n": 10, "mean_diff": 0.0055, "ci95": [-0.0117, 0.0228], "wins": 6, "ties": 0, "losses": 4, "wilcoxon_p": 0.4766}
- M9: {"n": 10, "mean_diff": 0.1172, "ci95": [-0.0304, 0.2788], "wins": 6, "ties": 0, "losses": 4, "wilcoxon_p": 0.1934}
- Confidence with 3 frames: {"n": 10, "mean_diff": 0.0558, "ci95": [-0.0208, 0.1336], "wins": 6, "ties": 0, "losses": 4, "wilcoxon_p": 0.2754}

## Every run (two seeds per prompt, when run)

| Run | Videos | Sections | Lasting conflicts | Broken attachments | Clean videos | Layout score | M9 |
|---|---|---|---|---|---|---|---|
| plain, seed 0 | 10 | 40 | 13 | 9 | 4 | 84.7 | 45.0 |
| blueprint, seed 0 | 10 | 39 | 8 | 2 | 7 | 85.2 | 56.8 |
| plain, seed 1 | 10 | 40 | 24 | 10 | 4 | 85.1 | 45.5 |
