# Prism W2 — status (corrected pass)

## What changed since the last delivery
Unifying the CLI (`run_pilot.py` now dispatches BFCL tasks to
`run_multiturn_attempt` automatically, by task `kind` — same flags,
one command for both suites) exposed two real bugs my own hand-built
smoke-test scripts had been silently working around:

1. **`bfcl_extracted.json` never actually saved `involved_classes`.**
   Every earlier "proof" worked only because my ad-hoc test scripts
   injected it manually in memory each time. Fixed at the source
   (`extract_bfcl.py`); both extracted files regenerated from the
   corrected scripts, not hand-patched.
2. **GSM8K tasks carried a vestigial `"tool_schemas": null`** placeholder
   left over from an abandoned idea. `schema_block` checked for the KEY
   being present, not the value being real, so it grabbed `None` and
   crashed. Fixed both ways: removed the dead placeholder at the source,
   and made `schema_block` check truthiness — defensive against this
   whole bug class recurring.

Both are now fixed at the root and reverified through six gates,
including — this time — the file exactly as delivered, through the real
CLI, with zero manual patching:
1. Full pilot regression — byte-identical to the long-standing known-good run.
2. GSM8K suite re-verified (`verify_suite.py`, 40/40).
3. GSM8K through `run_pilot.py` for real — dispatch, not a hand script.
4. BFCL through `run_pilot.py` for real, using the delivered file as-is.
5. A MIXED suite (one GSM8K task + one BFCL task, same JSON file) —
   proves dispatch happens per-task, not per-file: the GSM8K task got
   `numeric_exact` + the single-turn path, the BFCL task got
   `state_match` + the multi-turn path, correctly, side by side.
6. `scripts/smoke_test_bfcl.py` (the one with a REAL hand-built
   ground-truth script, proving correctness not just dispatch) still
   passes: exact replay succeeds, corrupted replay fails.

## The unified CLI (new)
```
python run_pilot.py --model mock --tasks prism/suite/w2_staging/gsm8k_extracted.json --limit 2
python run_pilot.py --model mock --tasks prism/suite/w2_staging/bfcl_extracted.json --limit 1
python run_pilot.py --model mlx  --tasks prism/suite/w2_staging/bfcl_extracted.json --limit 1 --seeds 1
```
The last line is the actual next step — a REAL model on a REAL BFCL
task. Everything proven so far is Mock-level (proves the harness logic);
this is the first time real generation meets the multi-turn control
flow and the stateful simulator. Expect some friction — the model has
never seen `json_react_v1.1` used for filesystem operations before, and
BFCL's tool descriptions are denser than the pilot's calculator/lookup.

## Unchanged from the previous status doc
n=53 decision, the PT-localization gap, the read-terminal state-check
caveat, the per-turn-vs-end-of-attempt checking scope — see the git
history of this file / previous session notes for that reasoning.
