# Layout complexity and faults, one tracker for every version

Tracker: c2vlab/scene_graph.py 277a060476c4, run with scene_graph.V2=False, layout.SAFE=False, layout.CROWDING=False.

| Version | Videos | Sections | Most objects on screen (mean) | Most text objects | Code lines | MVQS | Lasting conflicts | Broken attachments | Sections with a fault |
|---|---|---|---|---|---|---|---|---|---|
| local | 10 | 40 | 10.6 | 6.7 | 68 | 84.2 | 27 | 13 | 17/40 |
| local_claude_layout | 10 | 40 | 10.2 | 6.7 | 68 | 85.6 | 4 | 4 | 7/40 |
| qwen | 10 | 40 | 10.4 | 6.6 | 68 | 84.7 | 13 | 9 | 13/40 |
| qwen-anchor | 10 | 40 | 10.4 | 7.0 | 72 | 85.3 | 21 | 15 | 17/40 |
| haiku | 10 | 40 | 27.1 | 13.1 | 99 | 86.6 | 3 | 5 | 5/40 |
| sonnet | 10 | 40 | 20.6 | 11.3 | 62 | 86.4 | 1 | 10 | 7/40 |
| opus | 10 | 40 | 28.5 | 14.4 | 104 | 89.0 | 0 | 1 | 1/40 |
| sonnet-anchor | 10 | 40 | 21.4 | 12.1 | 70 | 86.9 | 0 | 4 | 2/40 |

Over 320 sections: rank correlation between the most objects on screen and faults (conflicts + broken attachments) -0.13 (p 0.024); code lines and faults -0.06 (p 0.33).
