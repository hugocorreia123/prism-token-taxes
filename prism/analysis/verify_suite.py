#!/usr/bin/env python3
"""Prism suite verifier — the W1 lesson made permanent.

A scripted mock validates the harness but is structurally blind to
ground truth (it agrees with whatever `expected` says). So every
numeric task must carry a `solution_expr`, and this script recomputes
`expected` from it with the same safe evaluator the calculator tool
uses. Run it before ANY pilot or confirmatory run:

    python -m prism.analysis.verify_suite prism/suite/pilot_tasks.json
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

from prism.harness.runner import _safe_eval


def main():
    path = Path(sys.argv[1] if len(sys.argv) > 1
                else "prism/suite/pilot_tasks.json")
    suite = json.loads(path.read_text())
    bad = 0
    for t in suite["tasks"]:
        if t.get("judge") != "numeric_exact":
            print(f"  {t['id']:14} non-numeric judge — skipped")
            continue
        expr = t.get("solution_expr")
        if not expr:
            bad += 1
            print(f"  {t['id']:14} MISSING solution_expr — untrusted")
            continue
        val = _safe_eval(ast.parse(expr, mode="eval"))
        ok = abs(float(val) - float(t["expected"])) < 1e-9
        mark = "ok" if ok else f"MISMATCH expr={val} expected={t['expected']}"
        if not ok:
            bad += 1
        print(f"  {t['id']:14} {mark}")
    if bad:
        print(f"\nVERIFY FAILED: {bad} task(s) untrusted — fix before running")
        sys.exit(1)
    print("\nsuite ground truth verified")


if __name__ == "__main__":
    main()
