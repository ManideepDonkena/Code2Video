"""Layout check and repair for one section: SGA's scene graph + Code2Video's ScopeRefine escalation.

    level "shift"   (code, no model) put `name.shift(v)` before the play where the conflict appears, v = the
                    minimum separation vector. SGA hands this vector to the LLM; we try it as code first.
    level "block"   (model) lines around the object's creation, with the conflict and the vector named.
    level "section" (model) the whole scene again, with every conflict named.
Each try is kept only if it runs and MVQS goes up (the incumbent is never lost).
"""

from __future__ import annotations

import ast
import json

from . import generate, mvqs
from .scene_graph import graph


def measure(path, cls, out):
    g = graph(path, cls, out)
    score = mvqs.mvqs(g["states"]) if g["states"] else None
    return g, (score or {}).get("mvqs", 0.0) if not g["error"] else 0.0, score


def describe(c):
    m = c["move"]
    what = f'{m["type"]} "{m.get("name")}" (created line {m.get("line")}, box {m["box"]})'
    if c.get("outside"):
        return f"{what} is outside the frame; shift it by {c['vector']}"
    s = c["stay"]
    return (f'{what} overlaps {s["type"]} "{s.get("name")}" (line {s.get("line")}, box {s["box"]}) by '
            f"{int(100 * c['ratio'])}%; moving it by {c['vector']} would clear it")  # fmt: skip


def shift_patch(code, c):
    name, line = c["move"].get("name"), c.get("after_line")
    if not name or not line:
        return None
    rows = code.splitlines()
    indent = rows[line - 1][: len(rows[line - 1]) - len(rows[line - 1].lstrip())]
    dx, dy = c["vector"]
    rows.insert(line - 1, f"{indent}{name}.shift({dx} * RIGHT + {dy} * UP)  # layout: separation vector")
    new = "\n".join(rows) + "\n"
    try:
        ast.parse(new)
    except SyntaxError:
        return None
    return new


def repair(section_id, out, rounds=3, log=print):
    path = out / "sections" / f"{section_id}.py"
    cls = section_id.upper()
    gpath = out / "sections" / f"{section_id}.graph.json"
    g, best, score = measure(path, cls, gpath)
    history = [{"level": "start", "mvqs": best, "conflicts": len(mvqs.persistent_conflicts(g["states"]))}]
    for _ in range(rounds):
        found = mvqs.persistent_conflicts(g["states"])
        if not found:
            break
        code = path.read_text()
        c = found[0]
        line = c["move"].get("line")
        tries = [("shift", shift_patch, (code, c))]
        if line:
            tries.append(("block", generate.patch_block, (code, line - 5, line + 5, describe(c))))
        tries.append(("section", generate.rewrite, (code, cls, "\n".join(describe(x) for x in found))))
        improved = False
        for level, make, args in tries:  # cheapest scope first (ScopeRefine)
            new = make(*args)
            if not new or new == code:
                continue
            path.write_text(new)
            g2, s2, score2 = measure(path, cls, gpath)
            if s2 > best:
                log(f"[layout] {section_id}: {level} fix kept, MVQS {best:.1f} -> {s2:.1f}")
                history.append({"level": level, "mvqs": s2, "conflict": describe(c)})
                g, best, score, improved = g2, s2, score2, True
                break
            path.write_text(code)
        if not improved:
            history.append({"level": "none kept", "conflict": describe(c)})
            break
    measure(path, cls, gpath)  # leave the graph of the kept code on disk
    (out / "sections" / f"{section_id}.layout.json").write_text(
        json.dumps({"score": score, "history": history}, indent=1)
    )
    return score, history
