"""Prism model adapters.

Design decision (spec v2.1): tool schemas are delivered IN-PROMPT and the
model replies with a small JSON protocol — never the provider's native
tool-calling API. This makes the Schema factor a pure token intervention,
identical across adapters, and sidesteps provider-specific tool-call
flakiness (the gpt-oss malformed-call failure mode).

Protocol (json_react_v1.1): the assistant replies with exactly one of
  {"tool": "<name>", "args": {...}}
  ANSWER: <final answer text>

Every adapter returns (text, tok_in, tok_out, tok_source, truncated).
tok_source: "api_usage" (Groq), "tokenizer_exact" (MLX), "mock" (CI only —
flagged non-confirmatory by analysis).
"""
from __future__ import annotations

import json
import os
import time

PROTOCOL = "json_react_v1.1"


class ChatResult:
    def __init__(self, text, tok_in, tok_out, tok_source, truncated=False):
        self.text = text
        self.tok_in = tok_in
        self.tok_out = tok_out
        self.tok_source = tok_source
        self.truncated = truncated


class MockModel:
    """Deterministic CI model driven by each task's explicit mock_script.
    Scripted on purpose: the mock proves the HARNESS, not intelligence,
    and its records carry tok_source='mock' so analysis excludes them
    from anything confirmatory."""

    provider = "mock"

    def __init__(self, model_id="mock-1"):
        self.model_id = model_id
        self._cursor = {}

    def start_attempt(self, task):
        self._cursor[task["id"]] = 0
        self._script = {task["id"]: task.get("mock_script", [])}

    def chat(self, messages, task, max_tokens=None, seed=0, temperature=0.0):
        i = self._cursor.get(task["id"], 0)
        script = task.get("mock_script", [])
        step = script[i] if i < len(script) else {"final": "ANSWER: unknown"}
        self._cursor[task["id"]] = i + 1
        if "tool" in step:
            text = json.dumps({"tool": step["tool"], "args": step["args"]})
        else:
            text = step["final"]
        tok_in = sum(len(str(m.get("content", ""))) for m in messages) // 4
        tok_out = max(1, len(text) // 4)
        truncated = max_tokens is not None and tok_out >= max_tokens
        return ChatResult(text, tok_in, tok_out, "mock", truncated)


class MLXModel:
    """Local Apple-Silicon adapter (mlx-lm). Tokenizer-exact accounting.
    NOTE: written for Hugo's Mac; cannot execute in the Linux build sandbox —
    smoke-test with: python run_pilot.py --model mlx --tasks prism/suite/pilot_tasks.json --limit 1
    """

    provider = "mlx"

    def __init__(self, model_id="mlx-community/Qwen2.5-3B-Instruct-4bit"):
        from mlx_lm import load  # lazy: only on the Mac
        self.model_id = model_id
        self.model, self.tokenizer = load(model_id)

    def start_attempt(self, task):
        pass

    def chat(self, messages, task, max_tokens=None, seed=0, temperature=0.2):
        from mlx_lm import generate
        from mlx_lm.sample_utils import make_sampler
        import mlx.core as mx
        mx.random.seed(int(seed))
        prompt = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True)
        tok_in = len(self.tokenizer.encode(prompt))
        cap = int(max_tokens) if max_tokens else 1024
        sampler = make_sampler(temp=float(temperature))
        text = generate(self.model, self.tokenizer, prompt=prompt,
                        max_tokens=cap, sampler=sampler, verbose=False)
        tok_out = len(self.tokenizer.encode(text))
        return ChatResult(text, tok_in, tok_out, "tokenizer_exact",
                          truncated=tok_out >= cap)


class GroqModel:
    """Groq validation arm. Token counts from the API usage field ONLY.
    TPM-aware: on 429/ratelimit it sleeps and retries; those waits are
    events, not token rows (no phantom costs). Groq exposes no sampling
    seed — seed_effective is recorded as None by the runner."""

    provider = "groq"
    seedless = True

    def __init__(self, model_id="openai/gpt-oss-120b"):
        from groq import Groq  # lazy
        self.model_id = model_id
        self.client = Groq(api_key=os.environ["GROQ_API_KEY"])
        self.on_rate_limit = None  # runner injects an event logger

    def start_attempt(self, task):
        pass

    def chat(self, messages, task, max_tokens=None, seed=None,
             temperature=0.2, max_retries=4):
        from groq import RateLimitError
        for i in range(max_retries):
            try:
                t0 = time.time()
                resp = self.client.chat.completions.create(
                    model=self.model_id, messages=messages,
                    max_tokens=int(max_tokens) if max_tokens else 1024,
                    temperature=float(temperature))
                u = resp.usage
                text = resp.choices[0].message.content or ""
                truncated = resp.choices[0].finish_reason == "length"
                return ChatResult(text, u.prompt_tokens, u.completion_tokens,
                                  "api_usage", truncated)
            except RateLimitError:
                wait = 20 * (i + 1)
                if self.on_rate_limit:
                    self.on_rate_limit({"wait_s": wait, "try": i + 1})
                time.sleep(wait)
        raise RuntimeError("groq: rate-limited beyond max_retries")


def make_model(name: str, model_id: str | None):
    if name == "mock":
        return MockModel(model_id or "mock-1")
    if name == "mlx":
        return MLXModel(model_id or "mlx-community/Qwen2.5-3B-Instruct-4bit")
    if name == "groq":
        return GroqModel(model_id or "openai/gpt-oss-120b")
    raise ValueError(f"unknown model backend: {name}")
