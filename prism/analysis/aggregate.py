#!/usr/bin/env python3
"""Prism analysis (W1): aggregate turn-level records into the attempt
table, print the per-cell summary, the paired all-on vs all-off RTW
contrast (with the non-inferiority gate), and the pilot power check.

Invariants enforced here, not assumed:
  - every attempt_summary's token totals equal the sum of its turn rows
  - every turn row carries a known tok_source
  - runs containing tok_source == 'mock' are labelled NON-CONFIRMATORY

Usage: python -m prism.analysis.aggregate results/<run>.jsonl [--power]
"""
from __future__ import annotations

import argparse
import json
import math
import statistics as stats
import sys
from collections import defaultdict
from pathlib import Path

DELTA_PP = 3.0  # non-inferiority margin, spec §4/§5


def load(path: Path):
    turns, attempts, events = [], [], []
    for line in path.read_text().splitlines():
        rec = json.loads(line)
        if rec.get("type") == "turn":
            turns.append(rec)
        elif rec.get("type") == "attempt_summary":
            attempts.append(rec)
        elif rec.get("type") == "event":
            events.append(rec)
    return turns, attempts, events


def check_invariants(turns, attempts):
    by_key = defaultdict(lambda: [0, 0])
    for t in turns:
        k = (t["task_id"], t["cell"], t["seed_effective"], t["attempt"])
        by_key[k][0] += t["tok_in"]
        by_key[k][1] += t["tok_out"]
        assert t["tok_source"] in ("api_usage", "tokenizer_exact", "mock"), \
            f"unknown tok_source in turn: {t['tok_source']}"
    bad = 0
    for a in attempts:
        k = (a["task_id"], a["cell"], a["seed_effective"], a["attempt"])
        ti, to = by_key.get(k, (None, None))
        if ti is None and a["outcome"] == "harness_error":
            continue
        if (ti, to) != (a["tok_in_total"], a["tok_out_total"]):
            bad += 1
            print(f"INVARIANT FAIL {k}: summary=({a['tok_in_total']},"
                  f"{a['tok_out_total']}) turns=({ti},{to})")
    assert bad == 0, f"{bad} attempts violate token-sum invariant"
    mock = any(a["tok_source"] == "mock" for a in attempts)
    return mock


def all_in_T(attempts, cell):
    """All-in tokens per success for one cell: every attempt's tokens
    (failures included) over the number of successes. Spec §4."""
    rows = [a for a in attempts
            if a["cell"] == cell and a["outcome"] != "harness_error"]
    tok = sum(a["tok_in_total"] + a["tok_out_total"] for a in rows)
    succ = sum(1 for a in rows if a["success"])
    return tok, succ, len(rows)


def per_cell_table(attempts, label=None):
    if label:
        print(f"--- {label} ---")
    cells = sorted({a["cell"] for a in attempts})
    print(f"{'cell':8} {'n':>3} {'succ':>4} {'acc%':>6} "
          f"{'tokens':>8} {'T (all-in/succ)':>16}")
    for c in cells:
        tok, succ, n = all_in_T(attempts, c)
        acc = 100 * succ / n if n else 0
        T = tok / succ if succ else float("inf")
        print(f"{c:8} {n:>3} {succ:>4} {acc:>6.1f} {tok:>8} {T:>16.1f}")


def check_source_heterogeneity(attempts):
    """A pooled T across GSM8K (short, single-turn) and BFCL (long,
    multi-turn) is a blend of two populations, not a meaningful
    statistic for either. Detect it and say so LOUDLY rather than let
    a pooled table quietly mean nothing — found the hard way while
    testing a real mixed suite."""
    sources = sorted({a.get("source", "pilot") for a in attempts})
    if len(sources) <= 1:
        return sources
    print(f"\n*** HETEROGENEOUS SUITE: {len(sources)} distinct task sources "
          f"({', '.join(sources)}) ***")
    print("The POOLED table below blends populations with different token "
          "profiles (e.g. GSM8K single-turn vs BFCL multi-turn) — treat it "
          "as a sanity check only. Per-source tables follow and are the "
          "numbers that mean something.\n")
    return sources


def paired_contrast(attempts):
    """all-on (S1B1) vs all-off (S0B0), per language, paired by task."""
    for L in (0, 1):
        on_c, off_c = f"S1B1L{L}", f"S0B0L{L}"
        tok_on, s_on, n_on = all_in_T(attempts, on_c)
        tok_off, s_off, n_off = all_in_T(attempts, off_c)
        if not (s_on and s_off):
            print(f"L{L}: insufficient successes for contrast")
            continue
        T_on, T_off = tok_on / s_on, tok_off / s_off
        rtw = 1 - T_on / T_off
        acc_on, acc_off = 100 * s_on / n_on, 100 * s_off / n_off
        gate = acc_on >= acc_off - DELTA_PP
        print(f"L{L}: T_off={T_off:.1f} T_on={T_on:.1f} "
              f"RTW={100*rtw:.1f}% | acc {acc_off:.1f}->{acc_on:.1f} | "
              f"gate(delta={DELTA_PP}pp): "
              f"{'PASS - claimable' if gate else 'FAIL - report frontier only'}")


def power_check(attempts, reduction=0.20, alpha=0.05, power=0.80):
    """Paired log-token variance from the pilot -> n for the core.
    Detectable effect: a `reduction` cut in all-in cost, i.e.
    delta = -log(1-reduction) on the paired log scale."""
    by_task = defaultdict(dict)
    for a in attempts:
        if a["outcome"] == "harness_error":
            continue
        tot = a["tok_in_total"] + a["tok_out_total"]
        if a["cell"].startswith("S1B1"):
            by_task[(a["task_id"], a["cell"][-2:])]["on"] = tot
        if a["cell"].startswith("S0B0"):
            by_task[(a["task_id"], a["cell"][-2:])]["off"] = tot
    diffs = [math.log(v["off"]) - math.log(v["on"])
             for v in by_task.values() if "on" in v and "off" in v
             and v["on"] > 0 and v["off"] > 0]
    if len(diffs) < 3:
        print("power: not enough paired items")
        return
    sd = stats.stdev(diffs)
    z_a, z_b = 1.959964, 0.841621
    delta = -math.log(1 - reduction)
    n = math.ceil(((z_a + z_b) * sd / delta) ** 2)
    print(f"power: paired sd(log-tokens)={sd:.3f} over {len(diffs)} pairs; "
          f"n needed for {int(power*100)}% power to detect "
          f"{int(reduction*100)}% reduction: {n} "
          f"({'fits' if n <= 80 else 'EXCEEDS'} the planned n=80)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results")
    ap.add_argument("--power", action="store_true")
    args = ap.parse_args()
    turns, attempts, events = load(Path(args.results))
    mock = check_invariants(turns, attempts)
    print(f"records ok: {len(turns)} turns, {len(attempts)} attempts"
          + ("  [MOCK RUN - NON-CONFIRMATORY]" if mock else ""))
    if events:
        kinds = defaultdict(int)
        for e in events:
            kinds[e["kind"]] += 1
        print("events:", dict(kinds))
        pv = defaultdict(int)
        for e in events:
            if e["kind"] == "protocol_violation":
                pv[e["detail"].get("cell", "?")] += 1
        if pv:
            print("protocol violations by cell:", dict(sorted(pv.items())))
    print()
    sources = check_source_heterogeneity(attempts)
    per_cell_table(attempts, label="POOLED (all sources)" if len(sources) > 1 else None)
    print()
    paired_contrast(attempts)
    if len(sources) > 1:
        for src_name in sources:
            sub = [a for a in attempts if a.get("source", "pilot") == src_name]
            print()
            per_cell_table(sub, label=f"source: {src_name}")
            print()
            paired_contrast(sub)
    if args.power:
        print()
        power_check(attempts)


if __name__ == "__main__":
    main()
