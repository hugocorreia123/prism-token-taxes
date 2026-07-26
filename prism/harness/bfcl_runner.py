"""Multi-turn runner for BFCL-derived stateful tasks (kind == "bfcl_multi_turn").

Deliberately a SEPARATE module, not a modification of runner.py's
run_attempt(). That function is the harness's most safety-critical path
(pilot tasks, GSM8K, and every hypothesis in the spec depend on it) and
was proven correct through the W1 forensics the hard way. A multi-turn,
stateful control-flow change belongs in new code with its own tests,
never retrofitted into a path everything else already trusts.

Design (reuses the EXISTING json_react_v1.1 protocol unchanged — no new
marker invented): each BFCL task carries `turns_en`/`turns_pt`, a list
of user messages. The harness appends turn N's message, lets the model
call tools (via the SAME parse_reply used everywhere else) until it
either emits "ANSWER: ..." (read here as "done acting for this turn,
here's my note to the user" — exactly how single-turn tasks already use
it) or hits a per-turn action cap, then appends turn N+1's message into
the SAME growing conversation. State persists across the whole attempt
in one simulator instance.

Judge: STATE-based, matching BFCL's own multi_turn_checker.py
methodology (state_checker via the simulator's own __eq__), not a
call-string match — see PRISM_W2 notes for why the naive approach was
rejected.
"""
from __future__ import annotations

import time

from .models import GroqRateLimitExhausted
from .accounting import RunWriter
from .runner import parse_reply, BASE_SYSTEM, CONCISION

MAX_ACTIONS_PER_TURN = 8

_ENV_FACTORIES = {}  # populated per simulator class as they're wired in


def register_env(class_name: str):
    def deco(factory):
        _ENV_FACTORIES[class_name] = factory
        return factory
    return deco


def _make_env(involved_classes: list[str], initial_config: dict):
    assert len(involved_classes) == 1, (
        "multi-simulator tasks are out of scope for this pass — see "
        "W2_STATUS.md; single-class only, deliberately")
    cls = involved_classes[0]
    assert cls in _ENV_FACTORIES, f"no env factory registered for {cls}"
    return _ENV_FACTORIES[cls](initial_config.get(cls, {}))


def judge_state(model_env, task: dict) -> tuple[str, dict]:
    """Compares the model's mutated environment against a freshly
    replayed ground-truth environment via the simulator's own __eq__ —
    the same technique BFCL's own state_checker uses. Checked once at
    the end of all turns (v1 simplification; per-turn checking is a
    named possible refinement, not done here — see W2_STATUS.md)."""
    from .bfcl_gorilla_env import replay_ground_truth  # lazy: keeps this
    gt_env = replay_ground_truth(task)                  # module simulator-agnostic
    ok = model_env == gt_env
    return ("success" if ok else "wrong"), {"state_match": ok}


def run_multiturn_attempt(model, task, factors, seed, temperature,
                          writer: RunWriter, attempt: int,
                          transcript_all: bool = False):
    from .runner import extract_first_json, schema_block  # reuse, not duplicate
    S, B, L = factors["S"], factors["B"], factors["L"]
    schemas_text, schema_variant, schema_hash = schema_block(task, S)
    system = BASE_SYSTEM + ("\n" + CONCISION if B == 1 else "")
    system += "\n\n" + schemas_text
    turns = task["turns_pt" if L == 1 else "turns_en"]
    seed_eff = None if getattr(model, "seedless", False) else seed

    env = _make_env(task["involved_classes"], task["initial_config"])
    messages = [{"role": "system", "content": system}]
    model.start_attempt(task)
    tok_in_tot, tok_out_tot, turn_idx, n_actions = 0, 0, 0, 0
    outcome, tok_source = None, "mock"
    executed_actions = []
    last_call, consecutive_repeats, repeat_flagged = None, 0, False

    for user_turn_i, user_msg in enumerate(turns):
        messages.append({"role": "user", "content": user_msg})
        for _ in range(MAX_ACTIONS_PER_TURN):
            turn_idx += 1
            t0 = time.time()
            try:
                res = model.chat(messages, task,
                                 max_tokens=(160 if B == 1 else None),
                                 seed=seed_eff or 0, temperature=temperature)
            except GroqRateLimitExhausted:
                # Daily quota gone — propagate so the whole run stops
                # cleanly instead of writing hundreds of harness_error
                # rows over hours. Resume with --resume after reset.
                raise
            except Exception as e:
                writer.event("model_error", {"task": task["id"], "err": str(e)})
                outcome = "harness_error"
                break
            tok_source = res.tok_source
            tok_in_tot += res.tok_in
            tok_out_tot += res.tok_out
            writer.turn(task_id=task["id"], factors=factors,
                        model=model.model_id, provider=model.provider,
                        seed=seed_eff, temperature=temperature,
                        attempt=attempt, turn_idx=turn_idx,
                        tok_in=res.tok_in, tok_out=res.tok_out,
                        tok_source=res.tok_source, schema_variant=schema_variant,
                        schema_hash=schema_hash, budget_cap=(160 if B == 1 else None),
                        latency_s=time.time() - t0)
            kind, payload, violated = parse_reply(res.text)
            if violated:
                writer.event("protocol_violation",
                             {"task": task["id"],
                              "cell": f"S{S}B{B}L{L}", "turn": turn_idx})
            messages.append({"role": "assistant", "content": res.text})
            if kind == "final":
                break  # this user-turn's actions are done
            if kind == "tool":
                n_actions += 1
                name, args = payload["tool"], payload["args"]
                call_sig = (name, tuple(sorted(args.items())))
                if call_sig == last_call:
                    consecutive_repeats += 1
                else:
                    consecutive_repeats = 1
                last_call = call_sig
                # Measurement only — never changes control flow. Same
                # principle as answer_without_tool: fires once at the
                # threshold, uniform across all cells, so it prices the
                # pathology instead of suppressing or biasing it.
                if consecutive_repeats == 3 and not repeat_flagged:
                    writer.event("repeated_identical_call",
                                {"task": task["id"],
                                 "cell": f"S{S}B{B}L{L}",
                                 "call": f"{name}({dict(call_sig[1])})",
                                 "turn": turn_idx})
                    repeat_flagged = True
                try:
                    result = getattr(env, name)(**args)
                    executed_actions.append((name, args))
                except Exception as e:
                    result = {"error": f"{type(e).__name__}: {e}"}
                messages.append({"role": "user",
                                 "content": f"TOOL RESULT: {result!r}"})
                continue
            messages.append({"role": "user", "content":
                             "Invalid format. Reply with one JSON tool "
                             "call or one 'ANSWER:' line."})
        if outcome == "harness_error":
            break

    if outcome != "harness_error":
        outcome, judge_detail = judge_state(env, task)
    else:
        judge_detail = {}

    if transcript_all or outcome != "success":
        writer.transcript(task_id=task["id"], factors=factors,
                          model=model.model_id, provider=model.provider,
                          seed=seed_eff, temperature=temperature,
                          attempt=attempt, outcome=outcome, messages=messages)
    writer.attempt_summary(
        task_id=task["id"], factors=factors, model=model.model_id,
        provider=model.provider, seed=seed_eff, temperature=temperature,
        attempt=attempt, outcome=outcome, judge="state_match",
        expected=judge_detail, got=[f"{n}({a})" for n, a in executed_actions],
        n_turns=turn_idx, tok_in_total=tok_in_tot, tok_out_total=tok_out_tot,
        tok_source=tok_source, source=task.get("source", "pilot"))
    return outcome
