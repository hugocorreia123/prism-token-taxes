# Vendored source: BFCL (Berkeley Function Calling Leaderboard)

`gorilla_file_system.py` and `long_context.py` are copied UNMODIFIED from
github.com/ShishirPatil/gorilla (berkeley-function-call-leaderboard/
bfcl_eval/eval_checker/multi_turn_eval/func_source_code/), licensed
Apache 2.0. Vendored here (rather than requiring a separate BFCL clone)
so Prism's harness runs standalone. Reason for reuse, not reimplementation:
this is the exact simulator BFCL's own state_checker grades against —
see PRISM_SPEC.md / W2_STATUS.md for why that beats a from-scratch stub.

## Disclosed modification (the ONLY change from upstream)

`gorilla_file_system.py` line ~6: the original package-relative import
(`from bfcl_eval.eval_checker.multi_turn_eval.func_source_code.long_context
import (...)`) was rewritten to a flat `from long_context import (...)`
so the file works standalone without vendoring BFCL's full package
hierarchy. No logic, class, or method was touched — verified by diff
against upstream before packaging (the discrimination + replay proofs
in W2_STATUS.md ran against this exact patched copy).
