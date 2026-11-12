"""Tables from the baseline run (``baseline.py``) and the MVQS run (``mvqs.py``): per lesson, overall, and how far the
judges and the runs agree. Prints a summary and writes ``summary.json`` next to the baseline results.

    python baseline/summarize.py --baseline <dir> --mvqs <dir>
"""

from __future__ import annotations

import argparse
import itertools
import json
import statistics as st
from pathlib import Path


def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(st.mean(xs), 1) if xs else None


def spearman(a, b):
    pairs = [(x, y) for x, y in zip(a, b, strict=True) if x is not None and y is not None]
    if len(pairs) < 4:
        return None

    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2
            i = j + 1
        return r

    ra, rb = ranks([p[0] for p in pairs]), ranks([p[1] for p in pairs])
    ma, mb = st.mean(ra), st.mean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb, strict=True))
    den = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    return round(num / den, 2) if den else None


def spread(values):
    """Largest difference between two runs of the same thing."""
    values = [v for v in values if v is not None]
    return max(abs(a - b) for a, b in itertools.combinations(values, 2)) if len(values) > 1 else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--mvqs", required=True)
    args = parser.parse_args()
    base, mv = Path(args.baseline), json.loads((Path(args.mvqs) / "mvqs.json").read_text(encoding="utf-8"))
    lessons = []
    for path in sorted(base.glob("*/result.json")):
        r = json.loads(path.read_text(encoding="utf-8"))
        row = {
            "id": r["id"],
            "topic": r["topic"],
            "language": r["language"],
            "quiz_kept": (r.get("quiz") or {}).get("kept"),
        }
        by = {}
        for s in r.get("student") or []:
            by.setdefault((s["model"], s["condition"]), []).append(s)
        for (model, cond), runs in by.items():
            tag = "g" if model.startswith("gemma") else "q"
            row[f"{tag}_{cond}"] = mean(s["score"] for s in runs)
            row[f"{tag}_{cond}_spread"] = spread([s["score"] for s in runs])
            if cond == "full" and tag == "g":
                row["g_evidence"] = mean(s.get("evidence_score") for s in runs)
                row["g_evidence_spread"] = spread([s.get("evidence_score") for s in runs])
                row["g_evidence_claude"] = mean(s.get("evidence_score_claude") for s in runs)
                row["g_null_full"] = mean(s["null"] for s in runs)
        for tag in ("g", "q"):
            if row.get(f"{tag}_full") is not None and row.get(f"{tag}_none") is not None:
                row[f"{tag}_teachquiz"] = round(row[f"{tag}_full"] - row[f"{tag}_none"], 1)
        for j in r.get("judges") or []:
            tag = {"gemma4:26b": "gemma", "qwen2.5vl:7b": "qwen", "claude-haiku-5-5": "claude"}.get(
                j["model"], j["model"]
            )
            row.setdefault(f"aes_{tag}", []).append(j["aes_avg"])
            row.setdefault(f"sga_{tag}", []).append(j["sga_avg"])
            for k, v in (j.get("aes") or {}).items():
                row.setdefault(f"aes_{tag}_{k}", []).append(v)
        for k in [k for k in row if k.startswith(("aes_", "sga_")) and isinstance(row[k], list)]:
            vals = row[k]
            row[k] = mean(vals)
            if k.count("_") == 1:
                row[k + "_spread"] = spread(vals)
        row.update({f"t_{k}": v for k, v in (r.get("timing") or {}).items()})
        m = mv.get(r["id"]) or {}
        row["mvqs"] = (m.get("score") or {}).get("mvqs")
        row["mvqs_intent"] = (m.get("score_intent") or {}).get("mvqs")
        lessons.append(row)

    keys = sorted(
        {k for row in lessons for k in row if isinstance(row.get(k), (int, float)) and k not in ("quiz_kept",)}
    )
    overall = {k: mean(row.get(k) for row in lessons) for k in keys}
    overall["n"] = len(lessons)
    by_lang = {}
    for lang in ("en-IN", "hinglish"):
        rows = [row for row in lessons if row["language"] == lang]
        by_lang[lang] = {
            "n": len(rows),
            **{
                k: mean(row.get(k) for row in rows)
                for k in (
                    "g_teachquiz",
                    "g_full",
                    "g_none",
                    "g_evidence",
                    "g_voice",
                    "g_pictures",
                    "aes_claude",
                    "mvqs_intent",
                )
            },
        }
    pick = lambda k: [row.get(k) for row in lessons]
    agreement = {
        "aes gemma~claude": spearman(pick("aes_gemma"), pick("aes_claude")),
        "aes qwen~claude": spearman(pick("aes_qwen"), pick("aes_claude")),
        "aes gemma~qwen": spearman(pick("aes_gemma"), pick("aes_qwen")),
        "sga claude~aes claude": spearman(pick("sga_claude"), pick("aes_claude")),
        "teachquiz~aes claude": spearman(pick("g_teachquiz"), pick("aes_claude")),
        "teachquiz~evidence": spearman(pick("g_teachquiz"), pick("g_evidence")),
        "evidence qwen-judge~claude-judge": spearman(pick("g_evidence"), pick("g_evidence_claude")),
        "teachquiz~picture change": spearman(pick("g_teachquiz"), pick("t_picture_change_share")),
        "teachquiz~speech over still": spearman(pick("g_teachquiz"), pick("t_speech_in_still_2s")),
        "evidence~picture change": spearman(pick("g_evidence"), pick("t_picture_change_share")),
        "mvqs~aes layout (claude)": spearman(pick("mvqs_intent"), pick("aes_claude_element_layout")),
        "teachquiz gemma~qwen": spearman(pick("g_teachquiz"), pick("q_teachquiz")),
    }
    spreads = {
        k: {"mean": mean(pick(k)), "max": max([x for x in pick(k) if x is not None], default=None)}
        for k in ("g_full_spread", "g_none_spread", "g_evidence_spread", "aes_gemma_spread", "aes_qwen_spread")
    }
    controls = {
        c: {
            "mean": mean(pick(f"g_{c}")),
            "lessons_at_or_below_10": sum(1 for x in pick(f"g_{c}") if x is not None and x <= 10),
        }
        for c in ("none", "first12", "other", "pictures", "voice", "full", "know")
    }
    summary = {
        "overall": overall,
        "by_language": by_lang,
        "agreement_spearman": agreement,
        "run_spread": spreads,
        "controls": controls,
        "lessons": lessons,
    }
    (base / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "lessons"}, indent=1))
    for row in lessons:
        print(
            row["id"],
            row["topic"][:28].ljust(28),
            row["language"][:5],
            "TQ",
            row.get("g_teachquiz"),
            "full",
            row.get("g_full"),
            "none",
            row.get("g_none"),
            "ev",
            row.get("g_evidence"),
            "evC",
            row.get("g_evidence_claude"),
            "voice",
            row.get("g_voice"),
            "pic",
            row.get("g_pictures"),
            "12s",
            row.get("g_first12"),
            "oth",
            row.get("g_other"),
            "| qTQ",
            row.get("q_teachquiz"),
            "| AES g/q/c",
            row.get("aes_gemma"),
            row.get("aes_qwen"),
            row.get("aes_claude"),
            "| MVQS",
            row.get("mvqs_intent"),
            "| chg",
            row.get("t_picture_change_share"),
            "still2s",
            row.get("t_speech_in_still_2s"),
        )


if __name__ == "__main__":
    main()
