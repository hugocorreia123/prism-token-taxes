#!/usr/bin/env python3
"""Reproduce the BFCL multi-turn harness proof locally.

    cd ~/Projects/prism && python scripts/smoke_test_bfcl.py

Runs the mock model through a REAL extracted BFCL task twice: once
replaying the exact ground truth (must succeed), once with one
mutating call corrupted (must fail). Proves run_multiturn_attempt(),
the vendored GorillaFileSystem simulator, and the state-based judge
all work end to end — using only files inside this repo, no external
BFCL clone needed.
"""
import ast
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import prism.harness.bfcl_gorilla_env  # noqa: registers GorillaFileSystem
from prism.harness.bfcl_runner import run_multiturn_attempt
from prism.harness.accounting import RunWriter, canonical_hash
from prism.harness.models import MockModel


def script_from_ground_truth(gt_turns, corrupt=False):
    calls = []
    for i, turn in enumerate(gt_turns):
        for call_str in turn:
            tree = ast.parse(call_str.strip(), mode="eval")
            name = tree.body.func.id
            args = {kw.arg: ast.literal_eval(kw.value)
                    for kw in tree.body.keywords}
            if corrupt and name == "mv" and "destination" in args:
                args = dict(args, destination="WRONG_PLACE")
            calls.append({"tool": name, "args": args})
        calls.append({"final": f"ANSWER: done with turn {i + 1}"})
    return calls


def main():
    tasks = json.loads(
        (Path(__file__).resolve().parent.parent / "suite" / "w2_staging"
         / "bfcl_extracted.json").read_text())["tasks"]
    task = dict(tasks[0])
    task["involved_classes"] = ["GorillaFileSystem"]  # single-class by construction

    out = Path("/tmp/bfcl_local_smoke")
    writer = RunWriter(out, {"model": "mock"}, canonical_hash("bfcl-local-smoke"))

    mock_ok = MockModel()
    task_ok = dict(task, mock_script=script_from_ground_truth(
        task["ground_truth_calls"]))
    mock_ok.start_attempt(task_ok)
    mock_ok._script = {task_ok["id"]: task_ok["mock_script"]}
    outcome_ok = run_multiturn_attempt(mock_ok, task_ok, {"S": 0, "B": 0, "L": 0},
                                       seed=0, temperature=0.0, writer=writer,
                                       attempt=1)

    mock_bad = MockModel()
    task_bad = dict(task, mock_script=script_from_ground_truth(
        task["ground_truth_calls"], corrupt=True))
    mock_bad.start_attempt(task_bad)
    mock_bad._script = {task_bad["id"]: task_bad["mock_script"]}
    outcome_bad = run_multiturn_attempt(mock_bad, task_bad, {"S": 0, "B": 0, "L": 0},
                                        seed=0, temperature=0.0, writer=writer,
                                        attempt=2)

    print(f"GorillaFileSystem resolved from: "
          f"{sys.modules['gorilla_file_system'].__file__}")
    print(f"Case A (exact ground-truth replay): {outcome_ok}  (expect: success)")
    print(f"Case B (one call corrupted):        {outcome_bad}  (expect: wrong)")
    ok = outcome_ok == "success" and outcome_bad == "wrong"
    print("\n" + ("PASS — harness proven on this machine" if ok
                  else "FAIL — see W2_STATUS.md and paste this output"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
