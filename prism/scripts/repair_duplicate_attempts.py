#!/usr/bin/env python3
"""Repair a results file that contains duplicate attempt numbers.

Why this exists: a resume bug (fixed) built its "already done" key from
the raw loop seed while the runner records `seed_effective=None` for
seedless providers (Groq exposes no sampling seed). The keys never
matched, so a resumed run re-executed cells that were already complete
and wrote them with `attempt=1` again — colliding with the originals.

The re-executed cells are NOT junk: they are genuine independent
measurements of the same condition. So rather than discarding them,
this renumbers each repeat sequentially (attempt 1, 2, 3...) together
with its turn and transcript records, which restores a unique
(task_id, cell, seed_effective, attempt) key and turns the collision
into extra replicates the analysis can legitimately use.

Writes <file>.repaired.jsonl and leaves the original untouched.

    python prism/scripts/repair_duplicate_attempts.py results/<run>.jsonl
"""
import json
import sys
from collections import defaultdict
from pathlib import Path


def key_of(rec):
    return (rec.get("task_id"), rec.get("cell"), rec.get("seed_effective"))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    src = Path(sys.argv[1])
    dest = src.with_suffix(".repaired.jsonl")

    counter = defaultdict(int)
    pending = defaultdict(list)   # buffered turn/transcript records per key
    out = []
    renumbered = 0
    backfilled = 0

    for line in src.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        rtype = rec.get("type")

        if rtype == "attempt_summary":
            k = key_of(rec)
            buffered = pending.pop(k, [])

            # A quota abort can leave turns with no closing summary. Because
            # the same seedless key collision defeated orphan-backfilling at
            # run time, those strays sit in front of the NEXT attempt's turns
            # and would otherwise be silently added to its token total.
            # Split them off by walking backward until the running sums match
            # what this summary actually claims.
            want_in = rec.get("tok_in_total", 0)
            want_out = rec.get("tok_out_total", 0)
            cum_in = cum_out = 0
            split, matched = 0, False
            for i in range(len(buffered) - 1, -1, -1):
                cum_in += buffered[i].get("tok_in", 0)
                cum_out += buffered[i].get("tok_out", 0)
                if cum_in == want_in and cum_out == want_out:
                    split, matched = i, True
                    break
            orphans = buffered[:split] if matched else []
            mine = buffered[split:] if matched else buffered
            if not matched and buffered:
                print(f"  NOTE: could not reconcile turn sums for {k} — "
                      f"left intact for manual review")

            if orphans:
                counter[k] += 1
                n_orphan = counter[k]
                for t in orphans:
                    t["attempt"] = n_orphan
                    out.append(t)
                synth = json.loads(json.dumps(rec))
                synth["attempt"] = n_orphan
                synth["outcome"] = "harness_error"
                synth["tok_in_total"] = sum(t.get("tok_in", 0) for t in orphans)
                synth["tok_out_total"] = sum(t.get("tok_out", 0) for t in orphans)
                synth["n_turns"] = len(orphans)
                synth["judge"] = "n/a"
                synth["expected"] = None
                synth["got"] = "interrupted mid-attempt (quota abort), recovered by repair"
                if "success" in synth:
                    synth["success"] = False
                out.append(synth)
                backfilled += 1

            counter[k] += 1
            n = counter[k]
            if n != rec.get("attempt"):
                renumbered += 1
            for t in mine:
                t["attempt"] = n
                out.append(t)
            rec["attempt"] = n
            out.append(rec)
        elif rtype in ("turn", "transcript") and rec.get("task_id"):
            pending[key_of(rec)].append(rec)
        else:
            out.append(rec)   # events, manifests, anything else: untouched

    # any turns with no closing summary (a crash mid-attempt) are kept
    # in place rather than silently dropped
    orphans = sum(len(v) for v in pending.values())
    for k, buffered in pending.items():
        out.extend(buffered)

    dest.write_text("\n".join(json.dumps(r, ensure_ascii=False)
                              for r in out) + "\n")

    summaries = [r for r in out if r.get("type") == "attempt_summary"]
    keys = [(r["task_id"], r["cell"], r["seed_effective"], r["attempt"])
            for r in summaries]
    repeats = {k: c for k, c in counter.items() if c > 1}

    print(f"read      : {src}")
    print(f"written   : {dest}")
    print(f"attempts  : {len(summaries)}  ({len(set(keys))} unique keys, "
          f"{len(keys) - len(set(keys))} duplicates remaining — must be 0)")
    print(f"renumbered: {renumbered} record(s)")
    if backfilled:
        print(f"orphaned partial attempts recovered as "
              f"harness_error: {backfilled}")
    print(f"cells with >1 measurement: {len(repeats)}"
          + (f"  (max {max(repeats.values())} repeats)" if repeats else ""))
    if orphans:
        print(f"orphaned turn/transcript records kept as-is: {orphans}")
    if len(keys) != len(set(keys)):
        print("\nWARNING: duplicates remain — do not use this file for analysis.")
        sys.exit(1)


if __name__ == "__main__":
    main()
