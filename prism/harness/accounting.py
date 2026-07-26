"""Prism accounting — the measurement layer.

Every model call emits one turn-level record; every attempt emits one
derived summary. Records are self-describing (hash-pinned to the suite,
config, and schema variant) and append-only behind a run manifest.
Token counts always carry their provenance (tok_source); estimates are
never silently mixed with exact counts.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path

HARNESS_VERSION = "0.1.0"

OUTCOMES = ("success", "wrong", "refusal", "truncated_at_cap", "harness_error")
TOK_SOURCES = ("api_usage", "tokenizer_exact", "mock")  # mock => non-confirmatory


def canonical_hash(obj) -> str:
    """Stable sha256 over canonical JSON — pins suites, configs, schemas."""
    blob = json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def new_run_id() -> str:
    return time.strftime("r%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]


class RunWriter:
    """Append-only JSONL writer with a manifest written first."""

    def __init__(self, out_dir: Path, config: dict, suite_hash: str):
        self.run_id = new_run_id()
        self.dir = Path(out_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / f"{self.run_id}.jsonl"
        self.config_hash = canonical_hash(config)
        self.suite_hash = suite_hash
        manifest = {
            "type": "manifest",
            "run_id": self.run_id,
            "harness_version": HARNESS_VERSION,
            "config": config,
            "config_hash": self.config_hash,
            "suite_hash": suite_hash,
            "ts": time.time(),
        }
        (self.dir / f"manifest_{self.run_id}.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False))

    @classmethod
    def resume(cls, existing_path: Path, config: dict, suite_hash: str):
        """Reopen an existing, interrupted run — same run_id, same
        file, continuing to append. Refuses loudly (not silently) if
        the resume attempt's config or suite doesn't exactly match
        the original run's manifest: resuming under a DIFFERENT
        model/budget/suite would silently mix incompatible conditions
        under one run_id, corrupting the dataset in a way nothing
        downstream would detect on its own."""
        existing_path = Path(existing_path)
        run_id = existing_path.stem
        manifest_path = existing_path.parent / f"manifest_{run_id}.json"
        if not manifest_path.exists():
            raise FileNotFoundError(
                f"no manifest_{run_id}.json next to {existing_path} — "
                f"cannot verify what this run actually was, refusing "
                f"to resume blind")
        manifest = json.loads(manifest_path.read_text())
        new_config_hash = canonical_hash(config)
        if manifest["config_hash"] != new_config_hash:
            raise ValueError(
                f"REFUSING to resume: config_hash mismatch "
                f"(original {manifest['config_hash']}, this attempt "
                f"{new_config_hash}) — resuming under a different "
                f"model/temperature/budget than the original run would "
                f"silently mix incompatible conditions under one run_id")
        if manifest["suite_hash"] != suite_hash:
            raise ValueError(
                f"REFUSING to resume: suite_hash mismatch "
                f"(original {manifest['suite_hash']}, this attempt "
                f"{suite_hash}) — the task suite has changed since "
                f"this run started")
        self = cls.__new__(cls)
        self.run_id = run_id
        self.dir = existing_path.parent
        self.path = existing_path
        self.config_hash = new_config_hash
        self.suite_hash = suite_hash
        # Record the resume event in the manifest for audit — never
        # overwrite the original ts, only note that a resume happened.
        manifest.setdefault("resumed_at", []).append(time.time())
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
        return self

    def _base(self, task_id: str, factors: dict, model: str, provider: str,
              seed, temperature: float, attempt: int) -> dict:
        return {
            "run_id": self.run_id,
            "harness_version": HARNESS_VERSION,
            "config_hash": self.config_hash,
            "suite_hash": self.suite_hash,
            "task_id": task_id,
            "cell": f"S{factors['S']}B{factors['B']}L{factors['L']}",
            "factors": factors,
            "model": model,
            "provider": provider,
            "seed_effective": seed,
            "temperature": temperature,
            "attempt": attempt,
            "ts": time.time(),
        }

    def turn(self, *, task_id, factors, model, provider, seed, temperature,
             attempt, turn_idx, tok_in, tok_out, tok_source, schema_variant,
             schema_hash, budget_cap, latency_s, retry_reason=None):
        assert tok_source in TOK_SOURCES, f"unknown tok_source {tok_source}"
        rec = self._base(task_id, factors, model, provider, seed,
                         temperature, attempt)
        rec.update({
            "type": "turn",
            "turn": turn_idx,
            "tok_in": int(tok_in),
            "tok_out": int(tok_out),
            "tok_source": tok_source,
            "schema_variant": schema_variant,
            "schema_hash": schema_hash,
            "budget_cap": budget_cap,
            "latency_s": round(float(latency_s), 3),
            "retry_reason": retry_reason,
        })
        self._append(rec)

    def attempt_summary(self, *, task_id, factors, model, provider, seed,
                        temperature, attempt, outcome, judge, expected, got,
                        n_turns, tok_in_total, tok_out_total, tok_source,
                        source="pilot"):
        assert outcome in OUTCOMES, f"unknown outcome {outcome}"
        rec = self._base(task_id, factors, model, provider, seed,
                         temperature, attempt)
        rec.update({
            "type": "attempt_summary",
            "outcome": outcome,
            "success": outcome == "success",
            "judge": judge,
            "expected": expected,
            "got": (str(got)[:400] if got is not None else None),
            "n_turns": n_turns,
            "tok_in_total": int(tok_in_total),
            "tok_out_total": int(tok_out_total),
            "tok_source": tok_source,
            "source": source,  # task provenance — lets analysis detect
                                # and refuse to silently pool heterogeneous
                                # task populations (GSM8K vs BFCL vs pilot)
        })
        self._append(rec)

    def transcript(self, *, task_id, factors, model, provider, seed,
                   temperature, attempt, outcome, messages, max_chars=600):
        """Failure forensics: full message list, each content capped.
        Written ONLY for non-success attempts — today's pilot proved that
        token counts alone cannot explain a failure."""
        rec = self._base(task_id, factors, model, provider, seed,
                         temperature, attempt)
        rec.update({"type": "transcript", "outcome": outcome,
                    "messages": [{"role": m["role"],
                                  "content": str(m.get("content", ""))[:max_chars]}
                                 for m in messages]})
        self._append(rec)

    def event(self, kind: str, detail: dict):
        """Non-cost events: rate-limit waits, harness notes. No token fields —
        a 429 that returned nothing must never mint a token row."""
        self._append({"type": "event", "run_id": self.run_id, "kind": kind,
                      "detail": detail, "ts": time.time()})

    def _append(self, rec: dict):
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def completed_keys(results_path: Path) -> set:
    """(task_id, cell, seed_effective) tuples that already have a real
    experimental outcome in an existing results file — for resume, to
    skip re-running what's genuinely done.

    Deliberately NOT counted as done: harness_error (the harness
    failed to get a real answer, not a valid observation — retry it)
    and skipped_pt_not_localized events (not an attempt at all). Both
    are eligible for resume to pick back up, same as anything never
    attempted."""
    path = Path(results_path)
    if not path.exists():
        return set()
    done = set()
    for line in path.read_text().splitlines():
        rec = json.loads(line)
        if (rec.get("type") == "attempt_summary"
                and rec.get("outcome") != "harness_error"):
            done.add((rec["task_id"], rec["cell"], rec["seed_effective"]))
    return done


def backfill_orphaned_and_next_attempt(writer: "RunWriter") -> dict:
    """A crash can land mid-attempt: turn records written, but the
    final summary never reached — a truncation the resume test caught
    directly. Those tokens were genuinely spent and must not go
    unaccounted for, but they also must not collide with the fresh
    re-run of that same (task,cell,seed).

    For every (task_id, cell, seed, attempt) with turns but no summary,
    writes a synthetic harness_error summary (same bucket as any other
    interrupted generation: reported, excluded from analysis, never
    invisible — model/provider/factors/tok_source read back from the
    orphaned turns themselves, not guessed). Returns the next-available
    attempt number per (task_id, cell, seed) — 1 if nothing exists yet,
    otherwise one past the highest attempt seen (including any just
    backfilled), so a fresh re-run can never reuse an attempt number
    that already has turn records under it."""
    if not writer.path.exists():
        return {}
    turns_by_key, summarized = {}, set()
    for line in writer.path.read_text().splitlines():
        rec = json.loads(line)
        if rec.get("type") == "turn":
            k = (rec["task_id"], rec["cell"], rec["seed_effective"], rec["attempt"])
            turns_by_key.setdefault(k, []).append(rec)
        elif rec.get("type") == "attempt_summary":
            summarized.add((rec["task_id"], rec["cell"],
                           rec["seed_effective"], rec["attempt"]))

    next_attempt = {}
    for (task_id, cell, seed, attempt), turns in turns_by_key.items():
        base = (task_id, cell, seed)
        next_attempt[base] = max(next_attempt.get(base, 1), attempt + 1)
        if (task_id, cell, seed, attempt) in summarized:
            continue
        S, B, L = int(cell[1]), int(cell[3]), int(cell[5])
        tok_in = sum(t["tok_in"] for t in turns)
        tok_out = sum(t["tok_out"] for t in turns)
        writer.attempt_summary(
            task_id=task_id, factors={"S": S, "B": B, "L": L},
            model=turns[0]["model"], provider=turns[0]["provider"],
            seed=seed, temperature=turns[0]["temperature"], attempt=attempt,
            outcome="harness_error", judge="n/a",
            expected=None, got="interrupted mid-attempt (crash/resume)",
            n_turns=len(turns), tok_in_total=tok_in, tok_out_total=tok_out,
            tok_source=turns[0]["tok_source"],
            source=turns[0].get("source", "pilot"))
        print(f"  backfilled orphaned attempt: {task_id} {cell} seed{seed} "
              f"attempt{attempt} ({tok_in + tok_out} tokens spent, "
              f"crash-interrupted, now recorded as harness_error)")
    return next_attempt
