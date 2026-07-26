#!/usr/bin/env python3
"""Comprehension check: EN vs PT-draft, before native post-edit.

The pilot's calcA_002 finding (PRISM_SPEC.md, W1 notes) showed a
FAITHFUL translation can still flip a small model's comprehension
entirely — back-translation review wouldn't have caught it. This
script operationalizes the protocol fix: run every task in both
languages and flag any large gap for a closer look BEFORE spending
review time polishing a translation whose problem isn't wording.

Flagging uses Fisher's exact test on each task's 2x2 (EN succ/fail x
PT succ/fail) table, NOT a raw percentage-gap threshold — a first
version used a flat 50-point-gap cutoff and, on a real MLX run at
n=4 per language, flagged 9/53 tasks; a proper accounting showed
pure sampling noise alone would produce ~11-16 flags at that n and
threshold, so the raw-gap version was barely better than chance.
Fisher's exact correctly discounts a large gap when n is too small
to distinguish it from noise, and reports it when the gap is genuinely
extreme relative to what n could produce.

Builds throwaway files under /tmp only — NEVER writes to
suite/w2_staging/*.json. A draft only becomes real, runnable PT
content when a human explicitly promotes it into content.pt /
turns_pt after review.

Usage:
    python scripts/comprehension_check.py --model mock   # CI proof
    python scripts/comprehension_check.py --model mlx     # real signal
    python scripts/comprehension_check.py --model mlx --seeds 3  # more power
"""
import argparse
import json
import subprocess
import sys
import tempfile
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def fisher_exact_2x2(a, b, c, d):
    """Exact two-sided p-value for [[a,b],[c,d]] via the hypergeometric
    tail — appropriate for the small n this check runs at; no scipy
    dependency needed for tables this size."""
    n = a + b + c + d
    row1, col1 = a + b, a + c
    row2 = c + d
    def p_table(x):
        b2, c2, d2 = row1 - x, col1 - x, row2 - (col1 - x)
        if b2 < 0 or c2 < 0 or d2 < 0:
            return 0.0
        return (comb(row1, x) * comb(row2, c2)) / comb(n, col1)
    p_obs = p_table(a)
    return sum(p_table(x) for x in range(0, min(row1, col1) + 1)
               if p_table(x) <= p_obs + 1e-12)


def build_check_suite(src_path: Path, draft_field_map: dict,
                      only: set | None = None) -> Path | None:
    """Copies a suite, substituting the draft translation into the
    REAL field the harness reads (content.pt / turns_pt) — but only in
    a temp file, never in the source. `only`, if given, keeps just
    those task ids — for a cheap, targeted rerun on a handful of
    already-flagged tasks instead of the whole suite. Returns None if
    the filter matches nothing in THIS suite (e.g. --only names only
    GSM8K ids while processing the BFCL file) — a real, legitimate
    case, not an error; the caller skips that suite rather than
    running run_pilot.py on an empty task list."""
    suite = json.loads(src_path.read_text())
    if only is not None:
        suite["tasks"] = [t for t in suite["tasks"] if t["id"] in only]
        if not suite["tasks"]:
            return None
    for t in suite["tasks"]:
        for real_field, draft_field in draft_field_map.items():
            if draft_field in t:
                t[real_field] = t[draft_field]
            elif "content" in t and draft_field in t.get("content", {}):
                t["content"][real_field] = t["content"][draft_field]
    fd, path = tempfile.mkstemp(suffix=".json", prefix="comprehension_")
    Path(path).write_text(json.dumps(suite, ensure_ascii=False))
    return Path(path)


def run_and_load(model, tasks_path, out_dir, seeds=1, transcript_all=False):
    cmd = [sys.executable, str(ROOT / "run_pilot.py"),
          "--model", model, "--tasks", str(tasks_path),
          "--seeds", str(seeds), "--out", str(out_dir)]
    if transcript_all:
        cmd.append("--transcript-all")
    subprocess.run(cmd, check=True, cwd=ROOT, capture_output=True, text=True)
    latest = sorted(out_dir.glob("*.jsonl"))[-1]
    return [json.loads(l) for l in latest.read_text().splitlines()
            if json.loads(l).get("type") == "attempt_summary"]


def collapse_by_seed(attempts):
    """S and B vary within a seed, but the 4 cells sharing one seed are
    NOT independent trials — a real MLX check showed them producing
    byte-identical output across all four (S,B) combinations at a
    fixed seed. Treating cell-count as sample size overstates power.
    This groups by seed_effective, checks whether S/B actually agreed
    (an inhomogeneous seed is itself a new, interesting finding, not
    hidden), and collapses each seed to ONE success/fail outcome —
    seeds, not cells, are the real unit of independent replication."""
    from collections import defaultdict
    by_seed = defaultdict(list)
    for a in attempts:
        by_seed[a["seed_effective"]].append(a["success"])
    n_success, inhomogeneous = 0, []
    for seed, outcomes in by_seed.items():
        if len(set(outcomes)) > 1:
            inhomogeneous.append(seed)
        n_success += sum(outcomes) > len(outcomes) / 2  # majority if split
    return len(by_seed), n_success, inhomogeneous


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="mock", choices=["mock", "mlx", "groq"])
    ap.add_argument("--seeds", type=int, default=1)
    ap.add_argument("--only", nargs="+", default=None,
                    help="Task ids to run (default: all). For a cheap, "
                         "targeted rerun on tasks already flagged.")
    ap.add_argument("--transcript-all", action="store_true",
                    help="Log every attempt's transcript, not just "
                         "failures — lets you compare the successful "
                         "trace against the failing one side by side.")
    ap.add_argument("--alpha", type=float, default=0.10,
                    help="Flag a task if Fisher's exact p < alpha. "
                         "0.10 (not the usual 0.05) because n is tiny "
                         "and the cost of a false negative here (an "
                         "unreviewed real gap) is worse than a false "
                         "positive (one extra transcript pull).")
    args = ap.parse_args()

    run_id = __import__("time").strftime("%Y%m%d_%H%M%S")
    out_base = ROOT / "results" / "comprehension_check" / run_id
    results = []

    gsm_draft = ROOT / "prism/suite/w2_staging/gsm8k_pt_draft.json"
    if gsm_draft.exists():
        only = set(args.only) if args.only else None
        check = build_check_suite(gsm_draft, {"pt": "pt_draft"}, only=only)
        if check is None:
            atts = []
        else:
            atts = run_and_load(args.model, check, out_base / "gsm",
                                seeds=args.seeds, transcript_all=args.transcript_all)
        for t in json.loads(gsm_draft.read_text())["tasks"]:
            en = [a for a in atts if a["task_id"] == t["id"]
                  and a["cell"].endswith("L0")]
            pt = [a for a in atts if a["task_id"] == t["id"]
                  and a["cell"].endswith("L1")]
            if en and pt:
                results.append((t["id"], "gsm8k", en, pt))

    bfcl_draft = ROOT / "prism/suite/w2_staging/bfcl_pt_draft.json"
    if bfcl_draft.exists():
        only = set(args.only) if args.only else None
        check = build_check_suite(bfcl_draft, {"turns_pt": "turns_pt_draft"}, only=only)
        if check is None:
            atts = []
        else:
            atts = run_and_load(args.model, check, out_base / "bfcl",
                                seeds=args.seeds, transcript_all=args.transcript_all)
        for t in json.loads(bfcl_draft.read_text())["tasks"]:
            en = [a for a in atts if a["task_id"] == t["id"]
                  and a["cell"].endswith("L0")]
            pt = [a for a in atts if a["task_id"] == t["id"]
                  and a["cell"].endswith("L1")]
            if en and pt:
                results.append((t["id"], "bfcl", en, pt))

    print(f"{'task':22} {'source':8} {'EN cell':>9} {'PT cell':>9} "
          f"{'EN seed':>9} {'PT seed':>9} {'gap':>6} {'Fisher p':>9}")
    flagged, inhomog_found = [], []
    for tid, src, en, pt in results:
        en_cell_s, pt_cell_s = (sum(a["success"] for a in en),
                                sum(a["success"] for a in pt))
        en_cell_n, pt_cell_n = len(en), len(pt)
        en_seeds, en_seed_s, en_bad = collapse_by_seed(en)
        pt_seeds, pt_seed_s, pt_bad = collapse_by_seed(pt)
        if en_bad or pt_bad:
            inhomog_found.append((tid, en_bad, pt_bad))
        gap = abs(en_seed_s / en_seeds - pt_seed_s / pt_seeds)
        # Fisher's exact on the SEED-level table — seeds are the real
        # unit of independent replication, not (S,B,seed) cells.
        p = fisher_exact_2x2(en_seed_s, en_seeds - en_seed_s,
                             pt_seed_s, pt_seeds - pt_seed_s)
        mark = " <-- FLAGGED" if p < args.alpha else ""
        if mark:
            flagged.append(tid)
        print(f"{tid:22} {src:8} {en_cell_s}/{en_cell_n:>5} "
              f"{pt_cell_s}/{pt_cell_n:>5} {en_seed_s}/{en_seeds:>5} "
              f"{pt_seed_s}/{pt_seeds:>5} {gap:>6.0%} {p:>9.3f}{mark}")

    print(f"\nfull records (including transcripts for any non-success "
          f"attempt) persisted under: {out_base}")
    print(f"\n{len(flagged)}/{len(results)} task(s) flagged "
          f"(Fisher's exact p < {args.alpha}, on SEED-level outcomes, "
          f"n={args.seeds} seed(s) per language — 'cell' columns are "
          f"context only, S/B collapsed since they're not independent "
          f"trials within a seed).")
    if inhomog_found:
        print(f"\n{len(inhomog_found)} task(s) where S/B did NOT agree "
              f"within some seed — itself a new finding, not hidden:")
        for tid, en_bad, pt_bad in inhomog_found:
            print(f"  {tid}: EN disagreement at seed(s) {en_bad}, "
                  f"PT disagreement at seed(s) {pt_bad}")
    if flagged:
        print("\nFlagged tasks are candidates for a comprehension-level "
              "issue, not necessarily a translation error — pull the "
              "transcripts (same forensic pattern as calcA_002/calcB_003) "
              "before assuming the draft PT is 'wrong'; it may be a "
              "faithful translation the model still can't parse.")
    if args.seeds == 1:
        print(f"\nNOTE: only 1 seed run — every flag above rests on a "
              f"single stochastic draw, replicated across S/B (which "
              f"empirically don't vary it). Real confidence needs "
              f"--seeds 5+ so 'seed' n is actually > 1.")
    if args.model == "mock":
        print("\n[MOCK RUN — proves the script's mechanics only; results "
              "are non-confirmatory. Run --model mlx for real signal.]")


if __name__ == "__main__":
    main()
