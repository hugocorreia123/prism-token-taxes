#!/usr/bin/env python3
"""Extract single-class (GorillaFileSystem-only) BFCL_v4 multi-turn tasks
into Prism-adjacent form, and build a STATE-BASED judge that reuses
BFCL's own simulator __eq__ — the same methodology BFCL's own
multi_turn_checker.py uses (state_checker), not a naive call-string
match, which would incorrectly fail equally-valid alternate orderings.

Ground-truth call strings ("cd(folder='document')") are parsed with
ast, never eval — no arbitrary code execution on data from disk.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

BFCL_ROOT = Path("/home/claude/w2_sources/bfcl/berkeley-function-call-leaderboard")
sys.path.insert(0, str(BFCL_ROOT))
from bfcl_eval.eval_checker.multi_turn_eval.func_source_code.gorilla_file_system import (
    GorillaFileSystem,
)


def parse_call(call_str: str):
    """'cd(folder=\"document\")' -> ('cd', {'folder': 'document'})
    via ast, so this never executes arbitrary code from the dataset."""
    tree = ast.parse(call_str.strip(), mode="eval")
    assert isinstance(tree.body, ast.Call), f"not a call: {call_str}"
    name = tree.body.func.id
    kwargs = {}
    for kw in tree.body.keywords:
        kwargs[kw.arg] = ast.literal_eval(kw.value)
    return name, kwargs


def adapt_schema(bfcl_schema: dict) -> dict:
    """BFCL's own schema shape, minimally adapted to standard JSON
    Schema (type: dict -> object) so compile_schema_v1 can compress it
    unmodified — no other field touched."""
    s = json.loads(json.dumps(bfcl_schema))
    if s.get("parameters", {}).get("type") == "dict":
        s["parameters"]["type"] = "object"
    s.pop("response", None)  # BFCL's return-shape doc; not part of the call contract
    return s


def replay(calls: list[tuple[str, dict]], initial_config: dict) -> GorillaFileSystem:
    fs = GorillaFileSystem()
    fs._load_scenario(initial_config.get("GorillaFileSystem", {}))
    for name, kwargs in calls:
        getattr(fs, name)(**kwargs)
    return fs


def main():
    items = [json.loads(l) for l in
             (BFCL_ROOT / "bfcl_eval/data/BFCL_v4_multi_turn_base.json")
             .read_text().splitlines()]
    answers = {json.loads(l)["id"]: json.loads(l)["ground_truth"] for l in
               (BFCL_ROOT / "bfcl_eval/data/possible_answer/BFCL_v4_multi_turn_base.json")
               .read_text().splitlines()}
    schema_lines = (BFCL_ROOT / "bfcl_eval/data/multi_turn_func_doc/gorilla_file_system.json").read_text().splitlines()
    tool_schemas = [adapt_schema(json.loads(l)) for l in schema_lines]

    single = [it for it in items if it["involved_classes"] == ["GorillaFileSystem"]]

    tasks, replay_ok, replay_fail = [], 0, 0
    for it in single:
        tid = it["id"]
        gt_turns_raw = answers[tid]
        gt_turns = [[parse_call(c) for c in turn] for turn in gt_turns_raw]
        all_calls = [c for turn in gt_turns for c in turn]

        # Sanity: replaying BFCL's OWN ground truth against BFCL's OWN
        # simulator must succeed with no execution errors — if this
        # fails, the bug is in my wiring, not in BFCL's data.
        try:
            fs_a = replay(all_calls, it["initial_config"])
            fs_b = replay(all_calls, it["initial_config"])
            assert fs_a == fs_b, "ground-truth replay is not even self-consistent"
            replay_ok += 1
        except Exception as e:
            replay_fail += 1
            print(f"  SKIP {tid}: replay failed — {type(e).__name__}: {e}")
            continue

        questions = [turn[0]["content"] for turn in it["question"]]
        tasks.append({
            "id": f"bfcl_{tid}",
            "kind": "bfcl_multi_turn",
            "source": "bfcl-v4-multi_turn_base",
            "judge": "state_match",
            "involved_classes": it["involved_classes"],
            "tool_schemas": tool_schemas,
            "initial_config": it["initial_config"],
            "turns_en": questions,
            "turns_pt": [None] * len(questions),  # MT draft filled separately
            "ground_truth_calls": gt_turns_raw,  # kept as raw strings for audit
        })

    out = Path("/home/claude/prism_w2/suite_raw/bfcl_extracted.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"tasks": tasks}, ensure_ascii=False, indent=1))

    print(f"\nsingle-class (GorillaFileSystem-only) base items: {len(single)}")
    print(f"ground-truth replay against BFCL's own simulator: "
          f"{replay_ok} ok, {replay_fail} failed")
    print(f"tool schemas adapted: {len(tool_schemas)}")
    print(f"written: {out}")

    # Discriminating-power proof: a WRONG sequence must NOT equal ground
    # truth. Must perturb a STATE-MUTATING call (mv/mkdir/touch/echo/rm) —
    # dropping a trailing READ (ls/cat/pwd/grep/tail/...) leaves state
    # unchanged by construction, which is correct behaviour, not a bug.
    MUTATORS = {"mv", "mkdir", "touch", "echo", "rm", "cp", "rename_file"}
    proved = False
    for t in single:
        gt = [parse_call(c) for turn in answers[t["id"]] for c in turn]
        mut_idx = next((i for i, (n, _) in enumerate(gt) if n in MUTATORS), None)
        if mut_idx is None:
            continue
        wrong = gt.copy()
        wrong[mut_idx] = ("pwd", {})  # replace a mutation with a harmless no-op read
        try:
            fs_gt = replay(gt, t["initial_config"])
            fs_wrong = replay(wrong, t["initial_config"])
        except Exception:
            continue
        print(f"\ndiscrimination check on {t['id']} (perturbed a "
              f"{gt[mut_idx][0]!r} call): states equal? {fs_gt == fs_wrong} "
              "(must be False)")
        assert fs_gt != fs_wrong, "judge cannot distinguish wrong from right!"
        print("state-based judge: proven to discriminate on a mutating action")
        proved = True
        break
    assert proved, "no single-class task had a mutating call to test against"
    print("\nCAVEAT (real, not hidden): state equality alone cannot detect a "
          "wrong FINAL action if that action is read-only (e.g. a wrong "
          "'tail' line-count) — BFCL's own harness pairs state_checker with "
          "a separate response_checker for exactly this case. W2 note: "
          "prefer mutating-final-action tasks for state_match, or add a "
          "response-content check for read-terminal ones later.")


if __name__ == "__main__":
    main()
