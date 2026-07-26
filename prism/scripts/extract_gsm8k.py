#!/usr/bin/env python3
"""Extract GSM8K-hard items into Prism task format.

GSM8K's own solutions carry <<lhs=result>> calculator annotations per
step. This script chains them into a single solution_expr and verifies
it via the SAME safe evaluator the harness's calculator tool uses —
nothing here is hand-typed ground truth (the W1 lesson, applied at
scale). Items that don't chain unambiguously are SKIPPED, not guessed.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "/home/claude/prism/prism")
from harness.runner import _safe_eval  # the exact evaluator the tool uses

ANNOT = re.compile(r"<<([^=<>]+)=(-?[\d.]+)>>")
FINAL = re.compile(r"####\s*(-?[\d,.]+)")


def parse_item(raw: dict):
    steps = [(m.group(1), float(m.group(2)))
             for m in ANNOT.finditer(raw["answer"])]
    fm = FINAL.search(raw["answer"])
    if not fm or not steps:
        return None
    final = float(fm.group(1).replace(",", ""))
    return raw["question"], steps, final


def chain_substitute(steps, final, tol=1e-6):
    """Walk backward from the last step, substituting each prior step's
    RESULT into the next expression wherever it appears as a standalone
    numeric token — unambiguously (exactly one occurrence) or not at
    all. Returns a solution_expr string, or None if it can't be built
    and verified cleanly."""
    if not steps:
        return None
    expr = steps[-1][0]
    for lhs, result in reversed(steps[:-1]):
        token = _fmt(result)
        pattern = r"(?<![\d.])" + re.escape(token) + r"(?![\d.])"
        hits = re.findall(pattern, expr)
        if len(hits) != 1:
            return None  # ambiguous or absent — do not guess
        expr = re.sub(pattern, f"({lhs})", expr, count=1)
    try:
        val = _safe_eval(ast.parse(expr, mode="eval"))
    except Exception:
        return None
    if abs(val - final) > tol:
        return None
    return expr


def _fmt(x: float) -> str:
    return str(int(x)) if x == int(x) else str(x)


def mock_script_for(steps, final):
    calls = [{"tool": "calculator", "args": {"expression": lhs}}
             for lhs, _ in steps]
    calls.append({"final": f"ANSWER: {_fmt(final)}"})
    return calls


def budget_cap_for(n_steps: int) -> int:
    return 160 + 40 * n_steps  # base + per-step overhead; refined at W2 pilot


def main():
    src = Path(sys.argv[1] if len(sys.argv) > 1
               else "/home/claude/w2_sources/gsm8k/grade_school_math/data/test.jsonl")
    min_steps = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    target_n = int(sys.argv[3]) if len(sys.argv) > 3 else 40

    candidates, seen, dropped = 0, 0, {"parse": 0, "chain": 0}
    tasks = []
    for line in src.read_text().splitlines():
        raw = json.loads(line)
        parsed = parse_item(raw)
        if not parsed:
            dropped["parse"] += 1
            continue
        question, steps, final = parsed
        if len(steps) < min_steps:
            continue
        candidates += 1
        expr = chain_substitute(steps, final)
        if expr is None:
            dropped["chain"] += 1
            continue
        seen += 1
        tid = f"gsm_{seen:03d}"
        tasks.append({
            "id": tid,
            "kind": "calc_qa",
            "source": "gsm8k-test",
            "n_steps": len(steps),
            "tools": ["calculator", "lookup"],  # resolved via RAW_SCHEMAS,
            "judge": "numeric_exact",              # same as the pilot suite
            "expected": final,
            "solution_expr": expr,
            "budget_cap": budget_cap_for(len(steps)),
            "lookup_table": {},  # decoy tool for this item — see PRISM_W2_NOTES
            "content": {
                "en": question.strip() + " Use the calculator for every "
                      "computation; reply with ANSWER: <number>.",
                "pt": None,  # MT DRAFT filled by translate_drafts.py — needs
                             # native post-edit before use (protocol, spec §3)
            },
            "mock_script": mock_script_for(steps, final),
        })
        if seen >= target_n:
            break

    out = Path("/home/claude/prism_w2/suite_raw/gsm8k_extracted.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"tasks": tasks}, ensure_ascii=False, indent=1))

    print(f"scanned for >= {min_steps}-step items")
    print(f"candidates ({min_steps}+ steps, annotations parsed): {candidates}")
    print(f"dropped — could not parse annotations at all: {dropped['parse']}")
    print(f"dropped — chain substitution ambiguous/unverifiable: {dropped['chain']}")
    print(f"ACCEPTED (machine-verified solution_expr): {len(tasks)}")
    print(f"written: {out}")


if __name__ == "__main__":
    main()
