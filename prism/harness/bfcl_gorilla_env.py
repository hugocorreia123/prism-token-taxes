"""GorillaFileSystem wiring for bfcl_runner.py — the only file that
imports BFCL's own simulator source. Kept separate so bfcl_runner.py
stays simulator-agnostic (registering a second class later, e.g.
TwitterAPI, means adding a file like this one, not editing this one or
bfcl_runner.py's control flow)."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "vendor" / "bfcl_source"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from gorilla_file_system import GorillaFileSystem  # vendored, see ATTRIBUTION.md
from .bfcl_runner import register_env


@register_env("GorillaFileSystem")
def _make(scenario: dict) -> GorillaFileSystem:
    fs = GorillaFileSystem()
    fs._load_scenario(scenario)
    return fs


def replay_ground_truth(task: dict) -> GorillaFileSystem:
    """Fresh env, ground-truth calls replayed in order — used only by
    judge_state() to build the comparison target. Ground-truth call
    strings are parsed via ast, never eval."""
    fs = GorillaFileSystem()
    fs._load_scenario(task["initial_config"].get("GorillaFileSystem", {}))
    for turn in task["ground_truth_calls"]:
        for call_str in turn:
            tree = ast.parse(call_str.strip(), mode="eval")
            name = tree.body.func.id
            kwargs = {kw.arg: ast.literal_eval(kw.value)
                     for kw in tree.body.keywords}
            getattr(fs, name)(**kwargs)
    return fs
