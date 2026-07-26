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
import re
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


class GroqRateLimitExhausted(RuntimeError):
    """Raised when the wait implied by a 429 is so long it means the
    DAILY quota is gone, not the per-minute one. Distinct from a
    transient throttle so the runner can stop cleanly instead of
    generating hundreds of harness_error rows over hours."""


class GroqModel:
    """Groq validation arm. Token counts from the API usage field ONLY.

    TPM-aware in the real sense: paces requests PROACTIVELY against a
    rolling 60-second token budget rather than only reacting to 429s.
    Measured the hard way — the free tier's 8,000 TPM for
    gpt-oss-120b allows only ~6 requests/minute at this workload's
    size, and an unpaced harness blows that within seconds, after
    which blind retries just hammer a closed door. Groq exposes no
    sampling seed — seed_effective is recorded as None by the runner.
    """

    provider = "groq"
    seedless = True

    def __init__(self, model_id="openai/gpt-oss-120b", tpm_budget=8000,
                 safety_frac=0.85):
        from groq import Groq  # lazy
        self.model_id = model_id
        # max_retries=0: OUR retry logic is the only layer. The SDK's
        # own internal retries otherwise fire first, invisibly, burning
        # quota before our handler ever sees the 429.
        self.client = Groq(api_key=os.environ["GROQ_API_KEY"], max_retries=0)
        self.on_rate_limit = None  # runner injects an event logger
        self.tpm_budget = tpm_budget * safety_frac
        self._window = []  # [(timestamp, tokens), ...] rolling 60s

    def _record_usage(self, tokens: int):
        self._window.append((time.time(), tokens))

    def _pace(self, estimated_tokens: int):
        """Sleep, if needed, so this request won't exceed the rolling
        60-second token budget. Prevention, not reaction."""
        while True:
            now = time.time()
            self._window = [(t, n) for t, n in self._window if now - t < 60]
            used = sum(n for _, n in self._window)
            if used + estimated_tokens <= self.tpm_budget or not self._window:
                return
            oldest = min(t for t, _ in self._window)
            sleep_s = max(1.0, 60 - (now - oldest) + 0.5)
            if self.on_rate_limit:
                self.on_rate_limit({"kind": "proactive_pace",
                                    "wait_s": round(sleep_s, 1),
                                    "window_tokens": used})
            time.sleep(sleep_s)

    @staticmethod
    def _estimate_tokens(messages, max_tokens) -> int:
        chars = sum(len(str(m.get("content", ""))) for m in messages)
        return int(chars / 3.5) + int(max_tokens or 1024)

    def start_attempt(self, task):
        pass

    def chat(self, messages, task, max_tokens=None, seed=None,
             temperature=0.2, max_retries=4):
        from groq import RateLimitError
        est = self._estimate_tokens(messages, max_tokens)
        self._pace(est)
        for i in range(max_retries):
            try:
                resp = self.client.chat.completions.create(
                    model=self.model_id, messages=messages,
                    max_tokens=int(max_tokens) if max_tokens else 1024,
                    temperature=float(temperature))
                u = resp.usage
                self._record_usage(u.prompt_tokens + u.completion_tokens)
                text = resp.choices[0].message.content or ""
                truncated = resp.choices[0].finish_reason == "length"
                return ChatResult(text, u.prompt_tokens, u.completion_tokens,
                                  "api_usage", truncated)
            except RateLimitError as e:
                wait = _retry_after_seconds(e)
                if wait is None:
                    wait = 20 * (i + 1)  # fallback only if no header
                # A wait this long means the DAILY cap, not the minute
                # one — retrying is pointless and would burn hours.
                if wait > 600:
                    raise GroqRateLimitExhausted(
                        f"groq: rate limit implies a {wait:.0f}s wait — "
                        f"daily quota is exhausted, not a transient "
                        f"throttle. Stopping cleanly; resume with "
                        f"--resume once the quota resets.") from e
                if self.on_rate_limit:
                    self.on_rate_limit({"kind": "retry_after",
                                        "wait_s": round(wait, 1),
                                        "try": i + 1})
                time.sleep(wait)
                self._window.clear()  # the window is stale after a long wait
        raise RuntimeError("groq: rate-limited beyond max_retries")


def _retry_after_seconds(exc) -> float | None:
    """Groq returns the exact wait in a retry-after header and/or in
    the error text ('Please try again in 6m 11.52s'). Use what the API
    actually says instead of guessing — the old fixed 20/40/60/80s
    ladder was both too short for a TPM window and blind to a TPD
    exhaustion."""
    resp = getattr(exc, "response", None)
    if resp is not None:
        hdr = getattr(resp, "headers", {}) or {}
        for key in ("retry-after", "x-ratelimit-reset-tokens",
                    "x-ratelimit-reset-requests"):
            val = hdr.get(key)
            if val:
                parsed = _parse_duration(str(val))
                if parsed is not None:
                    return parsed
    m = re.search(r"try again in ([0-9hms\.\s]+)", str(exc))
    if m:
        return _parse_duration(m.group(1))
    return None


def _parse_duration(s: str) -> float | None:
    """Parses '6m11.52s', '11.5s', '2m', or a bare number of seconds."""
    s = s.strip()
    try:
        return float(s)
    except ValueError:
        pass
    total, found = 0.0, False
    for value, unit in re.findall(r"([0-9]*\.?[0-9]+)\s*([hms])", s):
        found = True
        total += float(value) * {"h": 3600, "m": 60, "s": 1}[unit]
    return total if found else None


def make_model(name: str, model_id: str | None):
    if name == "mock":
        return MockModel(model_id or "mock-1")
    if name == "mlx":
        return MLXModel(model_id or "mlx-community/Qwen2.5-3B-Instruct-4bit")
    if name == "groq":
        return GroqModel(model_id or "openai/gpt-oss-120b")
    raise ValueError(f"unknown model backend: {name}")
