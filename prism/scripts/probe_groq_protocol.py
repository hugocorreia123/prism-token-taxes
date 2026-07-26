#!/usr/bin/env python3
"""Probe: can we stop gpt-oss-120b emitting NATIVE tool calls?

The blocker (measured, not guessed): Groq returns
    400 tool_use_failed — "Tool choice is none, but model called a tool"
    failed_generation: {"name": "calculator", "arguments": {...}}
The model ignores the in-prompt json_react protocol and emits a native
function call; Groq validates that server-side and rejects the request.
No usage data comes back, so these can't even be counted as attempts.

This tries four cheap variants (~5 requests total, negligible quota)
and reports which produce a clean, parseable reply:

  1. baseline        — current BASE_SYSTEM, gpt-oss-120b (expect 400)
  2. +prohibition    — same, plus an explicit "no function calling" line
  3. reworded        — "tool" vocabulary removed from the protocol text
  4. other model     — baseline prompt, llama-3.3-70b-versatile

Writes NOTHING to results/. Run:
    python prism/scripts/probe_groq_protocol.py
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from prism.harness.runner import BASE_SYSTEM, schema_block

PROHIBITION = (
    " CRITICAL: Do NOT use function calling, tool-calling APIs, or any "
    "structured tool-call format. Your reply must be ordinary plain text "
    "containing the JSON object literally, as text."
)

# Same protocol shape, but with the vocabulary that primes function
# calling ("tool", "call a tool") removed — worth isolating, since the
# trigger may be the wording rather than the schemas themselves.
REWORDED = (
    "You are a precise assistant. Below is a list of available actions. "
    'To take an action, reply with EXACTLY one JSON object like '
    '{"tool": "<name>", "args": {...}} and nothing else — as plain text, '
    "not as a function call. When you have the final answer, reply with "
    "exactly one line: ANSWER: <answer>. After a TOOL RESULT, continue "
    "with your NEXT single action using that result. Never answer from "
    "memory of your own earlier expressions - if a calculation is "
    "needed, use the calculator action."
)


def build_messages(task, system_text):
    schemas_text, _, _ = schema_block(task, S=0)
    system = system_text + "\n\n" + schemas_text
    return [{"role": "system", "content": system},
            {"role": "user", "content": task["content"]["en"]}]


def try_variant(client, label, model_id, messages):
    print(f"\n--- {label}  [{model_id}] ---")
    try:
        resp = client.chat.completions.create(
            model=model_id, messages=messages, max_tokens=512,
            temperature=0.2)
        text = resp.choices[0].message.content or ""
        u = resp.usage
        print(f"  OK  ({u.prompt_tokens} in / {u.completion_tokens} out)")
        print(f"  reply: {text[:200]!r}")
        looks_right = text.strip().startswith("{") or "ANSWER:" in text
        print(f"  parseable by our protocol: {'YES' if looks_right else 'NO'}")
        return "ok" if looks_right else "wrong_format"
    except Exception as e:
        msg = str(e)
        if "tool_use_failed" in msg or "model called a tool" in msg:
            print("  FAILED — native tool call rejected (the known blocker)")
        else:
            print(f"  FAILED — {type(e).__name__}: {msg[:200]}")
        return "failed"


def main():
    if not os.environ.get("GROQ_API_KEY"):
        print("GROQ_API_KEY not set."); sys.exit(1)
    from groq import Groq
    client = Groq(api_key=os.environ["GROQ_API_KEY"], max_retries=1)

    suite = json.loads(
        (ROOT / "prism/suite/w2_staging/gsm8k_extracted.json").read_text())
    task = suite["tasks"][0]
    print(f"probe task: {task['id']}")

    results = {}
    results["1. baseline"] = try_variant(
        client, "1. baseline (current prompt)", "openai/gpt-oss-120b",
        build_messages(task, BASE_SYSTEM))
    results["2. +prohibition"] = try_variant(
        client, "2. baseline + explicit prohibition", "openai/gpt-oss-120b",
        build_messages(task, BASE_SYSTEM + PROHIBITION))
    results["3. reworded"] = try_variant(
        client, "3. reworded (no tool-calling vocabulary)",
        "openai/gpt-oss-120b", build_messages(task, REWORDED))
    results["4. other model"] = try_variant(
        client, "4. baseline prompt, different model",
        "llama-3.3-70b-versatile", build_messages(task, BASE_SYSTEM))
    results["5. other model + prohibition"] = try_variant(
        client, "5. different model + prohibition",
        "llama-3.3-70b-versatile", build_messages(task, BASE_SYSTEM + PROHIBITION))

    print("\n" + "=" * 55)
    for k, v in results.items():
        print(f"  {k:32} -> {v}")
    workable = [k for k, v in results.items() if v == "ok"]
    print("=" * 55)
    if workable:
        print(f"\nWORKABLE: {', '.join(workable)}")
        print("Cheapest workable option becomes M2's configuration — but "
              "note any prompt change strictly applies to BOTH arms for "
              "comparability (see the tradeoff discussion).")
    else:
        print("\nNONE worked. M2 on Groq is likely not viable with the "
              "in-prompt protocol; document as a limitation, or test "
              "another provider.")


if __name__ == "__main__":
    main()
