#!/usr/bin/env python3
"""Prism W1 pilot runner.

Examples:
  python run_pilot.py --model mock                       # CI: harness proof
  python run_pilot.py --model mlx --limit 2 --seeds 1    # Mac smoke test
  python run_pilot.py --model mlx                        # full pilot, M1
"""
from __future__ import annotations

import argparse
import itertools
import json
import random
import sys
from pathlib import Path

from prism.harness.accounting import (RunWriter, canonical_hash,
                                      completed_keys, backfill_orphaned_and_next_attempt)
from prism.harness.models import make_model, PROTOCOL, GroqRateLimitExhausted
from prism.harness.runner import run_attempt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=["mock", "mlx", "groq"])
    ap.add_argument("--model-id", default=None)
    ap.add_argument("--tasks", default="prism/suite/pilot_tasks.json")
    ap.add_argument("--out", default="results")
    ap.add_argument("--seeds", type=int, default=1)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--transcript-all", action="store_true",
                    help="Diagnostic only: log every attempt's full "
                         "transcript, not just failures. Off by default "
                         "so confirmatory runs stay lean.")
    ap.add_argument("--budget-cap-default", type=int, default=192,
                    help="Provisional pilot cap; spec sets 1.5x median "
                         "correct-solution length after the pilot.")
    ap.add_argument("--resume", default=None,
                    help="Path to an existing results .jsonl from an "
                         "interrupted run of the SAME suite+config — "
                         "skips (task,cell,seed) combos that already "
                         "have a real outcome, continues into the same "
                         "file. Refuses if config/suite don't match.")
    args = ap.parse_args()

    suite = json.loads(Path(args.tasks).read_text())
    tasks = suite["tasks"][: args.limit] if args.limit else suite["tasks"]
    suite_hash = canonical_hash(suite)

    model = make_model(args.model, args.model_id)
    config = {"model": args.model, "model_id": model.model_id,
              "protocol": PROTOCOL, "temperature": args.temperature,
              "seeds": args.seeds, "n_tasks": len(tasks),
              "budget_cap_default": args.budget_cap_default,
              "tasks_file": args.tasks}
    writer = (RunWriter.resume(Path(args.resume), config, suite_hash)
             if args.resume else RunWriter(Path(args.out), config, suite_hash))
    already_done = completed_keys(args.resume) if args.resume else set()
    next_attempt = backfill_orphaned_and_next_attempt(writer) if args.resume else {}
    if args.resume:
        print(f"RESUMING {writer.path}: {len(already_done)} (task,cell,seed) "
              f"combo(s) already have a real outcome, will be skipped.")
    if hasattr(model, "on_rate_limit"):
        model.on_rate_limit = lambda d: writer.event("rate_limit", d)

    # Lazy: only pull in the BFCL/simulator path if this suite actually
    # needs it — GSM8K and pilot suites never import bfcl_gorilla_env.
    run_multiturn_attempt = None
    if any(t.get("kind") == "bfcl_multi_turn" for t in tasks):
        import prism.harness.bfcl_gorilla_env  # noqa: registers the env
        from prism.harness.bfcl_runner import run_multiturn_attempt

    def pt_available(task: dict) -> bool:
        """Kind-aware check: is this task's Portuguese content real, or
        still the localization placeholder? Checked BEFORE any model
        call — an L=1 cell against null content is a fully predictable,
        deterministic dead end, never a real experimental outcome, and
        should never cost a real generation to discover."""
        if task.get("kind") == "bfcl_multi_turn":
            turns = task.get("turns_pt") or []
            return bool(turns) and all(t is not None for t in turns)
        return task.get("content", {}).get("pt") is not None

    cells = [dict(S=s, B=b, L=l) for s, b, l
             in itertools.product([0, 1], [0, 1], [0, 1])]
    total = len(tasks) * len(cells) * args.seeds
    done = 0
    skipped_pt = 0
    for task in tasks:
        # Randomize (cell, seed) execution order per task — a free
        # confound guard (server load, thermal throttling over a long
        # run) the spec commits to (PRISM_SPEC.md §5). Deterministically
        # seeded from the task id so the exact order is reproducible,
        # not just "random and undocumented".
        order = [(factors, seed) for factors in cells
                for seed in range(args.seeds)]
        random.Random(f"cellorder:{task['id']}").shuffle(order)
        for factors, seed in order:
                done += 1
                cell = f"S{factors['S']}B{factors['B']}L{factors['L']}"
                # Seedless providers (Groq exposes no sampling seed) are
                # recorded with seed_effective=None, so the resume key must
                # be built the SAME way the runner builds it. Comparing the
                # raw loop `seed` against a stored None silently matches
                # nothing and re-runs everything — a real bug that cost a
                # full day of API quota before it was caught.
                seed_eff = None if getattr(model, "seedless", False) else seed
                if (task["id"], cell, seed_eff) in already_done:
                    print(f"[{done}/{total}] {task['id']} {cell} seed{seed} "
                          f"-> already done, resuming past it")
                    continue
                if factors["L"] == 1 and not pt_available(task):
                    skipped_pt += 1
                    writer.event("skipped_pt_not_localized",
                                {"task": task["id"],
                                 "cell": f"S{factors['S']}B{factors['B']}L1"})
                    print(f"[{done}/{total}] {task['id']} "
                          f"S{factors['S']}B{factors['B']}L1 seed{seed} "
                          f"-> SKIPPED (PT not yet localized for this task)")
                    continue
                attempt_n = next_attempt.get((task["id"], cell, seed_eff), 1)
                if task.get("kind") == "bfcl_multi_turn":
                    outcome = run_multiturn_attempt(
                        model, task, factors, seed, args.temperature,
                        writer, attempt=attempt_n, transcript_all=args.transcript_all)
                else:
                    outcome = run_attempt(model, task, factors, seed,
                                          args.temperature, writer, attempt=attempt_n,
                                          budget_cap_default=args.budget_cap_default,
                                          transcript_all=args.transcript_all)
                print(f"[{done}/{total}] {task['id']} "
                      f"S{factors['S']}B{factors['B']}L{factors['L']} "
                      f"seed{seed} -> {outcome}")
    if skipped_pt:
        print(f"\n{skipped_pt} cell(s) skipped — Portuguese content not "
              f"yet localized for the affected task(s). Run with "
              f"--tasks pointed at a suite whose content.pt / turns_pt "
              f"is filled in once localization is done.")
    print(f"\nrun {writer.run_id} written to {writer.path}")


if __name__ == "__main__":
    try:
        main()
    except GroqRateLimitExhausted as e:
        # Designed stop, not a crash. Results are append-only and
        # already on disk, so nothing is lost — print something
        # actionable instead of a 40-line traceback.
        print(f"\n{'=' * 60}\nSTOPPED: daily API quota exhausted.\n{'=' * 60}")
        print(f"{e}\n")
        print("Everything completed so far is saved. Resume once the "
              "quota resets (Groq's TPD is a rolling 24h window, so "
              "wait ~a day from the FIRST request of the run, not from "
              "this message) with the same command plus:")
        print('  --resume "$(ls -t results/*.jsonl | head -1)"')
        sys.exit(0)
