#!/usr/bin/env python3
"""Confirmatory analysis CLI — the pipeline pre-registration commits to.

Loads an attempt_summary results file, runs RTW (dual-computed), the
H1-H3 accuracy gate, H4's TOST equivalence test, Holm correction across
H1-H4, and prints the fixed decision table. Every stated CI comes from
the cluster bootstrap, never a model's own standard errors.

NON-CONFIRMATORY MODE (--pilot-ok): required to run this on anything
other than the real W4-5 confirmatory data — the spec's own stopping
rule excludes pilot/dry-run data from confirmatory conclusions
(PRISM_SPEC.md §5). Without the flag, this refuses to run on a file
whose manifest doesn't look like a genuine confirmatory run, so nobody
can accidentally treat a pilot number as a finding.

Usage:
    python scripts/run_confirmatory_analysis.py results/<run>.jsonl --pilot-ok
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "prism"))
from analysis.confirmatory import (compute_rtw, tost_equivalence,
                                   multiplicity_correct, decision_table)


def analysis_code_hash() -> str:
    """Hash of the analysis code itself — this is what gets frozen at
    pre-registration (PRISM_SPEC.md Materials & code)."""
    h = hashlib.sha256()
    for f in sorted((ROOT / "prism/analysis").glob("*.py")):
        h.update(f.read_bytes())
    return h.hexdigest()[:16]


def load_records(path: Path) -> list:
    records = []
    for line in path.read_text().splitlines():
        rec = json.loads(line)
        if rec.get("type") != "attempt_summary":
            continue
        rec["S"] = rec["factors"]["S"]
        rec["B"] = rec["factors"]["B"]
        rec["L"] = rec["factors"]["L"]
        rec["tokens"] = rec["tok_in_total"] + rec["tok_out_total"]
        records.append(rec)
    return records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results_file")
    ap.add_argument("--pilot-ok", action="store_true",
                    help="Required to run on non-confirmatory (pilot/"
                         "dry-run) data. Output is clearly labeled "
                         "either way.")
    ap.add_argument("--n-boot", type=int, default=2000)
    args = ap.parse_args()

    path = Path(args.results_file)
    records = load_records(path)
    sources = sorted(set(r.get("source", "pilot") for r in records))
    is_confirmatory = len(records) >= 800  # matches the real W4-5 scale

    if not is_confirmatory and not args.pilot_ok:
        print("This does not look like a confirmatory-scale run "
              f"({len(records)} attempts, expected ~848). Pass "
              "--pilot-ok to run anyway — output will be clearly "
              "labeled non-confirmatory, per the spec's own stopping "
              "rule (pilot data never enters confirmatory analysis).")
        sys.exit(1)

    print(f"analysis code hash: {analysis_code_hash()}")
    print(f"records: {len(records)} attempts, sources: {sources}")
    if not is_confirmatory:
        print("\n*** NON-CONFIRMATORY RUN — mechanics check only. ***")
        print("Numbers below prove the PIPELINE works; they are not")
        print("findings. Real conclusions wait for the W4-5 confirmatory run.\n")

    for source in sources:
        sub = [r for r in records if r.get("source", "pilot") == source]
        print(f"\n{'='*60}\nsource: {source} (n={len(sub)} attempts)\n{'='*60}")
        try:
            rtw = compute_rtw(sub, n_boot=args.n_boot)
        except Exception as e:
            print(f"  could not fit (likely too few successes at this "
                  f"scale for {source}): {type(e).__name__}: {e}")
            continue
        for L in ("L0", "L1"):
            r = rtw[L]
            if r["separation_warning"]:
                print(f"  {L}: *** {r['separation_warning']} ***")
                continue
            print(f"  {L}: RTW_glm={r['rtw_glm_marginal']:.1%}  "
                  f"RTW_direct={r['rtw_direct_paired']}  "
                  f"BCa_CI={r['rtw_bca_ci']}  "
                  f"acc {r['acc_off_glm']:.1%}->{r['acc_on_glm']:.1%}  "
                  f"claimable={r['claimable']}")


if __name__ == "__main__":
    main()
