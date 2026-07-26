"""Prism runner — applies a factorial cell to a task and executes the
agent loop under the in-prompt JSON tool protocol, emitting turn-level
records and a derived attempt summary.

Cell application:
  S=0 raw schemas in-prompt | S=1 compiled schemas (pilot compiler v0;
      frozen v1.0 replaces it in W2 — schema_hash pins whichever ran)
  B=0 free reasoning        | B=1 concision line + hard max_tokens cap
  L=0 English user content  | L=1 Portuguese user content
      (system + schemas stay English in ALL cells — spec §2)
"""
from __future__ import annotations

import ast
import json
import operator as op
import re
import time

from .accounting import RunWriter, canonical_hash
from .models import GroqRateLimitExhausted

MAX_TURNS = 6
BASE_SYSTEM = (
    "You are a precise assistant. You may use the tools listed below. "
    "To call a tool, reply with EXACTLY one JSON object like "
    '{"tool": "<name>", "args": {...}} and nothing else. '
    "When you have the final answer, reply with exactly one line: "
    "ANSWER: <answer>. "
    "After a TOOL RESULT, continue with your NEXT single action using "
    "that result. Never answer from memory of your own earlier "
    "expressions - if a calculation is needed, call the calculator "
    "with the actual returned values."
)
CONCISION = ("Be maximally concise. No explanations, no restating the "
             "problem. Go straight to tool calls and the final answer.")

# ---------------------------------------------------------------- tools
_ALLOWED = {ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul,
            ast.Div: op.truediv, ast.FloorDiv: op.floordiv,
            ast.Mod: op.mod, ast.Pow: op.pow, ast.USub: op.neg}


def _safe_eval(node):
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED:
        return _ALLOWED[type(node.op)](_safe_eval(node.left),
                                       _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED:
        return _ALLOWED[type(node.op)](_safe_eval(node.operand))
    raise ValueError("disallowed expression")


def run_tool(name: str, args: dict, task: dict) -> str:
    if name == "calculator":
        try:
            val = _safe_eval(ast.parse(str(args.get("expression", "")),
                                       mode="eval"))
            return json.dumps({"result": val})
        except Exception as e:
            return json.dumps({"error": f"bad expression: {e}"})
    if name == "lookup":
        table = task.get("lookup_table", {})
        key = str(args.get("key", ""))
        return json.dumps({"value": table.get(key, None)})
    return json.dumps({"error": f"unknown tool {name}"})


# ------------------------------------------------------------- schemas
RAW_SCHEMAS = {
    "calculator": {
        "name": "calculator",
        "description": ("Evaluates a single arithmetic expression and "
                        "returns its numeric result. Supports addition, "
                        "subtraction, multiplication, division, floor "
                        "division, modulo and exponentiation with "
                        "parentheses. Use this tool for every non-trivial "
                        "numeric computation instead of computing in your "
                        "head, to avoid arithmetic mistakes."),
        "parameters": {"type": "object", "properties": {"expression": {
            "type": "string",
            "description": ("The arithmetic expression to evaluate, for "
                            "example '(12.5 * 4) - 7'. Digits, "
                            "operators and parentheses only.")}},
            "required": ["expression"]},
    },
    "lookup": {
        "name": "lookup",
        "description": ("Looks up a value by key in this task's reference "
                        "table and returns it. Use it whenever the "
                        "problem refers to a named quantity, price, or "
                        "rate that is not stated in the text."),
        "parameters": {"type": "object", "properties": {"key": {
            "type": "string",
            "description": "The exact key to look up."}},
            "required": ["key"]},
    },
}


def compile_schema_v0_pilot(schema: dict) -> dict:
    """PILOT compiler v0 — description-stripping placeholder used in W1.
    Kept (not deleted) so pilot-run schema_hashes stay reproducible."""
    s = json.loads(json.dumps(schema))
    s["description"] = s["description"].split(".")[0] + "."
    for p in s["parameters"]["properties"].values():
        p.pop("description", None)
    return s


_FILLER = (
    "use this tool whenever", "this tool is useful for", "this is useful",
    "use this when", "you should call this when", "call this tool",
    "you must use", "always use this",
)

# Deontic / constraint markers — a clause containing any of these is
# safety-relevant and is NEVER trimmed away, regardless of length.
# W2 finding: BFCL's mv.destination clause "...cannot be a path" sat
# past v1.0's 35-char cap and got silently cut — the exact clause that
# would have prevented the model's compound-path failure mode. General
# list, not overfit to that one case.
_CONSTRAINT_MARKERS = (
    "cannot", "can not", "must not", "must be", "must ", "should not",
    "only if", "only when", "required", "requires", "not allowed",
    "not permitted", "exactly", "at least", "at most", "no more than",
    "no less than", "always ", "never ",
)

# A SECOND, distinct category — v1.2, found via a real MLX task
# (gsm_024): calculator's dropped third sentence ("...instead of
# computing in your head, to avoid arithmetic mistakes") isn't a
# deontic constraint, it's PURPOSIVE guidance — why to prefer one
# behavior over another. Measured effect on that one task: S0 (raw)
# 10/10 seed-level success vs S1 (compiled) 4/10, replicated across
# 5 independent seeds. A distinct linguistic category from
# _CONSTRAINT_MARKERS, kept separate so each is independently
# auditable rather than folded into one undifferentiated list.
_PURPOSE_MARKERS = (
    "instead of", "rather than", "to avoid", "in order to", "so that",
    "to ensure", "to prevent", "to make sure",
)


def _is_constraint(clause: str) -> bool:
    low = clause.lower()
    return any(m in low for m in _CONSTRAINT_MARKERS)


def _is_purposive(clause: str) -> bool:
    low = clause.lower()
    return any(m in low for m in _PURPOSE_MARKERS)


def _is_load_bearing(clause: str) -> bool:
    return _is_constraint(clause) or _is_purposive(clause)


def _trim(text: str, cap: int) -> tuple[str, bool]:
    """Clause-aware: the first clause and EVERY constraint-bearing
    clause are always kept in full; only the remaining filler/
    elaboration clauses are subject to the cap. Returns (text,
    constraint_found) — the second value feeds the audit report.
    Never returns empty."""
    if not text:
        return text, False
    clauses = [c.strip() for c in text.split(". ") if c.strip()]
    if not clauses:
        return text, False

    first = clauses[0]
    low = first.lower()
    for f in _FILLER:
        if low.startswith(f):
            first = first[len(f):].strip(" ,:-")
            break

    constraint_clauses = [c for c in clauses[1:] if _is_load_bearing(c)]
    filler_clauses = [c for c in clauses[1:] if not _is_load_bearing(c)]

    kept = [first] + constraint_clauses
    remaining_budget = max(0, cap - sum(len(c) for c in kept))
    for c in filler_clauses:
        if remaining_budget <= 0:
            break
        piece = c[:remaining_budget].rsplit(" ", 1)[0] or c[:remaining_budget]
        if piece:
            kept.append(piece)
            remaining_budget -= len(piece)

    out = ". ".join(k.rstrip(".") for k in kept if k) + "."
    return out, bool(constraint_clauses)


def compile_schema_v1(schema: dict, _audit: list | None = None) -> dict:
    """FROZEN structure-aware schema compressor, v1.2 (v1.1 preserved
    deontic constraints only; this adds purposive-clause preservation
    after the gsm_024 finding — see PRISM_SPEC.md §6 and
    W2_STATUS.md for the audit trail).

    Never touched: tool name, parameter names, types, `required`, enum
    values. Compressed: prose only — but any clause containing a
    constraint marker is now ALWAYS retained in full, never subject to
    the length cap. Output stays standard JSON Schema shape.

    `_audit`, if a list is passed, gets one dict per compressed field
    appended: {schema, field, constraint_found, before_len, after_len}
    — used by scripts/audit_compiler.py, not by the harness at runtime.
    """
    s = json.loads(json.dumps(schema))  # deep copy, never mutate input
    if "description" in s:
        before = s["description"]
        s["description"], found = _trim(before, 70)
        if _audit is not None:
            _audit.append({"schema": schema.get("name"), "field": "description",
                           "constraint_found": found, "before_len": len(before),
                           "after_len": len(s["description"])})
    props = s.get("parameters", {}).get("properties", {})
    for pname, p in props.items():
        if "description" in p:
            before = p["description"]
            p["description"], found = _trim(before, 35)
            if _audit is not None:
                _audit.append({"schema": schema.get("name"), "field": f"param:{pname}",
                               "constraint_found": found, "before_len": len(before),
                               "after_len": len(p["description"])})
    return s


def schema_block(task: dict, S: int) -> tuple[str, str, str]:
    # Real W2 tasks embed their own schemas (BFCL brings dozens of
    # distinct tools); pilot tasks resolve names against the small
    # global RAW_SCHEMAS registry. Both supported so the pilot suite
    # keeps running unchanged.
    if task.get("tool_schemas"):
        schemas = task["tool_schemas"]
    else:
        schemas = [RAW_SCHEMAS[t] for t in task["tools"]]
    variant = "raw"
    if S == 1:
        schemas = [compile_schema_v1(s) for s in schemas]
        variant = "compiled_v1.0"
    text = "TOOLS:\n" + "\n".join(
        json.dumps(s, ensure_ascii=False, separators=(",", ":"))
        if variant != "raw" else json.dumps(s, ensure_ascii=False)
        for s in schemas)
    return text, variant, canonical_hash(schemas)


# -------------------------------------------------------------- judges
def _norm_number(s: str) -> str:
    """Locale-aware: '1,234.5' -> '1234.5' (comma = thousands) but
    '138,006' with no dot -> '138.006' (European decimal comma).
    The W1 pilot showed PT answers being mangled by US-only stripping."""
    s = s.strip()
    if "," in s and "." in s:
        return s.replace(",", "")
    if "," in s:
        return s.replace(",", ".")
    return s


def judge(task: dict, transcript: list, final_text: str | None):
    kind = task["judge"]
    if kind == "numeric_exact":
        if not final_text:
            return "wrong", None
        m = re.search(r"ANSWER:\s*(-?[\d.,]+)", final_text)
        if not m:
            return "wrong", final_text
        got = _norm_number(m.group(1))
        try:
            ok = abs(float(got) - float(task["expected"])) < 1e-6
        except ValueError:
            return "wrong", got
        return ("success" if ok else "wrong"), got
    if kind == "toolcall_match":
        want = task["expected_call"]
        for t in transcript:
            if (t.get("tool") == want["tool"]
                    and t.get("args") == want["args"]):
                return "success", json.dumps(t)
        return "wrong", json.dumps(transcript[-1]) if transcript else None
    return "harness_error", f"unknown judge {kind}"


def extract_first_json(text: str):
    """First balanced JSON object in text (string-aware), plus whether
    anything else surrounded it. The W1 pilot showed the 3B chaining
    calls as {A}>{B}>{C}; the old greedy regex swallowed the lot and
    starved the model of its own (correct) first lookup."""
    start = text.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            c = text[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            else:
                if c == '"':
                    in_str = True
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        cand = text[start:i + 1]
                        try:
                            obj = json.loads(cand)
                            extra = bool(text[:start].strip()
                                         or text[i + 1:].strip())
                            return obj, extra
                        except json.JSONDecodeError:
                            break
        start = text.find("{", start + 1)
    return None, False


def parse_reply(text: str):
    """('tool', payload, violated) | ('final', text, False) |
    ('malformed', text, False). A valid first tool object wins even in a
    chained reply — executed, with the violation logged as a measured
    event (uniform policy: biases no factor, quantifies discipline)."""
    stripped = text.strip()
    obj, extra = extract_first_json(stripped)
    if obj is not None and "tool" in obj:
        return "tool", {"tool": obj["tool"],
                        "args": obj.get("args", {})}, extra
    if "ANSWER:" in stripped:
        return "final", stripped, False
    return "malformed", stripped, False


# -------------------------------------------------------------- attempt
def run_attempt(model, task, factors, seed, temperature, writer: RunWriter,
                attempt: int, budget_cap_default: int,
                transcript_all: bool = False):
    S, B, L = factors["S"], factors["B"], factors["L"]
    schemas_text, schema_variant, schema_hash = schema_block(task, S)
    system = BASE_SYSTEM + ("\n" + CONCISION if B == 1 else "")
    system += "\n\n" + schemas_text
    content = task["content"]["pt" if L == 1 else "en"]
    cap = (task.get("budget_cap", budget_cap_default) if B == 1 else None)
    seed_eff = None if getattr(model, "seedless", False) else seed

    messages = [{"role": "system", "content": system},
                {"role": "user", "content": content}]
    model.start_attempt(task)
    tool_calls, tok_in_tot, tok_out_tot = [], 0, 0
    calc_ok = 0
    last_call, consecutive_repeats, repeat_flagged = None, 0, False
    outcome, final_text, tok_source = None, None, "mock"

    for turn_idx in range(1, MAX_TURNS + 1):
        t0 = time.time()
        try:
            res = model.chat(messages, task, max_tokens=cap,
                             seed=seed_eff or 0, temperature=temperature)
        except GroqRateLimitExhausted:
            # Daily quota gone — propagate so the whole run stops cleanly
            # instead of writing hundreds of harness_error rows over
            # hours. Resume with --resume once the quota resets.
            raise
        except Exception as e:
            writer.event("model_error", {"task": task["id"], "err": str(e)})
            outcome, final_text = "harness_error", str(e)
            break
        tok_source = res.tok_source
        tok_in_tot += res.tok_in
        tok_out_tot += res.tok_out
        writer.turn(task_id=task["id"], factors=factors,
                    model=model.model_id, provider=model.provider,
                    seed=seed_eff, temperature=temperature, attempt=attempt,
                    turn_idx=turn_idx, tok_in=res.tok_in, tok_out=res.tok_out,
                    tok_source=res.tok_source, schema_variant=schema_variant,
                    schema_hash=schema_hash, budget_cap=cap,
                    latency_s=time.time() - t0)
        if res.truncated:
            messages.append({"role": "assistant", "content": res.text})
            if cap is not None:
                outcome, final_text = "truncated_at_cap", res.text
            else:
                writer.event("safety_cap_hit",
                             {"task": task["id"], "turn": turn_idx})
                final_text = res.text
            break
        kind, payload, violated = parse_reply(res.text)
        if violated:
            writer.event("protocol_violation",
                         {"task": task["id"],
                          "cell": f"S{S}B{B}L{L}", "turn": turn_idx})
        if kind == "final":
            messages.append({"role": "assistant", "content": res.text})
            final_text = payload
            break
        if kind == "tool":
            tool_calls.append(payload)
            call_sig = (payload["tool"], tuple(sorted(payload["args"].items())))
            if call_sig == last_call:
                consecutive_repeats += 1
            else:
                consecutive_repeats = 1
            last_call = call_sig
            if consecutive_repeats == 3 and not repeat_flagged:
                writer.event("repeated_identical_call",
                             {"task": task["id"], "cell": f"S{S}B{B}L{L}",
                              "call": f"{payload['tool']}({dict(call_sig[1])})",
                              "turn": turn_idx})
                repeat_flagged = True
            tool_out = run_tool(payload["tool"], payload["args"], task)
            if payload["tool"] == "calculator" and '"result"' in tool_out:
                calc_ok += 1
            messages.append({"role": "assistant", "content": res.text})
            messages.append({"role": "user",
                             "content": f"TOOL RESULT: {tool_out}"})
            continue
        messages.append({"role": "assistant", "content": res.text})
        messages.append({"role": "user", "content":
                         "Invalid format. Reply with one JSON tool call "
                         "or one 'ANSWER:' line."})

    if outcome is None:
        outcome, got = judge(task, tool_calls, final_text)
    else:
        got = final_text

    if (task.get("solution_expr") and calc_ok == 0
            and final_text and "ANSWER:" in str(final_text)):
        writer.event("answer_without_tool",
                     {"task": task["id"],
                      "cell": f"S{S}B{B}L{L}", "turn": turn_idx})

    if outcome != "success" or transcript_all:
        writer.transcript(task_id=task["id"], factors=factors,
                          model=model.model_id, provider=model.provider,
                          seed=seed_eff, temperature=temperature,
                          attempt=attempt, outcome=outcome,
                          messages=messages)
    writer.attempt_summary(
        task_id=task["id"], factors=factors, model=model.model_id,
        provider=model.provider, seed=seed_eff, temperature=temperature,
        attempt=attempt, outcome=outcome, judge=task["judge"],
        expected=task.get("expected", task.get("expected_call")),
        got=got, n_turns=len(tool_calls) + 1,
        tok_in_total=tok_in_tot, tok_out_total=tok_out_tot,
        tok_source=tok_source, source=task.get("source", "pilot"))
    return outcome
