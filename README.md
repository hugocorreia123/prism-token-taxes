# Prism — a factorial decomposition of recoverable token waste

**Question:** agentic LLM workloads waste tokens in at least three ways — verbose tool
schemas, unbounded reasoning, and non-English input inflating token counts. If you
attack all three at once, how much waste is actually *recoverable*, and does the
saving survive contact with accuracy?

**Short answer, on the models tested:** on a 3B model, not at all — the optimizations
cost more than they save and break accuracy badly. On a 70B model, the same
optimizations are absorbed without visible damage. **The waste is real; recovering
it appears to be model-scale-dependent.**

This is a negative result for the original hypotheses, and the more interesting
finding sits in the gap between the two models.

---

## Headline findings

**1. The interventions failed on the small model, in two different ways.**
On Qwen2.5-3B (848 attempts, n=53 tasks × 2 seeds), the fully-optimized condition
was worse than baseline in every arm. In English it cost accuracy catastrophically;
in Portuguese it cost tokens without paying for itself.

| Suite · language | RTW (tokens/success) | 95% BCa CI | Accuracy off → on | Claimable? |
|---|---|---|---|---|
| GSM8K · EN | −109.7% | (−336.6%, −3.2%) | 31.3% → 16.2% | **no** — gate failed |
| GSM8K · PT | −22.0% | (−163.2%, +33.9%) | 23.8% → 21.3% | gate passed, CI spans zero |
| BFCL · EN | −102.2% | (−637.6%, +14.2%) | 15.4% → 3.8% | **no** — gate failed |
| BFCL · PT | +28.8% | (+5.0%, +47.9%) | 7.7% → 7.7% | yes — but on 2 successes/arm |

Negative RTW means the "optimized" condition burned *more* tokens per successful
task than the baseline. The accuracy gate (non-inferiority, δ = 3pp) blocks any
efficiency claim when accuracy drops — which it does, hard, in both English arms.

**2. The collapse did not transfer to a larger model.**
Re-running the GSM8K arm on llama-3.3-70b: *(partial — 53 of 96 attempts, quota-limited)*

- **50/53 successes (~94%)** vs ~31% for the 3B model in the equivalent baseline cell
- The three failures landed in `S0B1L1`, `S0B1L0`, `S1B0L1` — **zero failures in any
  `S1B1` cell**, the exact condition that collapsed the small model from 31% to 16%

*(Full M2 grid pending — numbers above will be replaced once the remaining 43
attempts complete.)*

**3. A live Schema × Budget interaction, replicated.**
Task `gsm_024` succeeded 10/10 in English with raw schemas, and failed *every* seed
when compressed schemas and a reasoning budget were applied together — while either
factor alone was survivable. This is direct candidate evidence for H4, the
interaction hypothesis, and it reproduced across three independent runs and two
separate code paths.

**4. Language effects are real but not directional.**
Three tasks showed complete, seed-stable language splits — and they don't point the
same way. `gsm_029` succeeded 5/5 in Portuguese while failing 5/5 in English (the
English run hallucinated a multiplication with no basis in the problem). `gsm_039`
did the reverse. Both had faithful translations that a native reviewer approved
unchanged. This argues against a simple "non-English tax" and toward
task-idiosyncratic comprehension failures.

---

## Design

A 2×2×2 within-task factorial, every task run in all eight cells:

| Factor | Off (0) | On (1) |
|---|---|---|
| **S** — Schema | raw JSON Schema tool definitions | compressed via a frozen compiler (v1.2) |
| **B** — Budget | unbounded reasoning | capped output budget + concision instruction |
| **L** — Language | English user content | Portuguese user content |

Schemas and system prompts stay English in every cell, so **L** isolates user-content
language rather than confounding it with prompt language.

**Primary metric: all-in tokens per success** — every attempt's tokens (including
failures') divided by successes. A method that saves tokens by failing more often
gets no credit. Recoverable Token Waste is `RTW = 1 − T_on/T_off`, claimable only if
accuracy passes a δ = 3pp non-inferiority gate.

**Suite (n = 53), composed from validated sources rather than invented:**
- **40 GSM8K-hard items** (≥3 reasoning steps), wrapped with calculator + lookup
  tools. Ground truth is auto-derived from GSM8K's own `<<expr=result>>` annotations
  and machine-verified — never hand-typed. 69 candidates yielded 40 acceptances;
  29 were dropped as unverifiable rather than guessed at.
- **13 BFCL-v4 multi-turn tasks** (single-simulator-class only). Every ground-truth
  trajectory replays cleanly against BFCL's own simulator before acceptance.
- **Portuguese localization**: MT draft → native review → *model-level comprehension
  check*. 53/53 drafts approved verbatim (0% edit rate).

The last step replaced a planned back-translation check for a concrete reason: the
pilot found a case where a *faithful* translation still flipped the model's
comprehension entirely. Back-translation cannot catch that; running the model on
both languages can.

**Analysis** (`prism/analysis/`): negative-binomial GLM for tokens, logistic GLM for
accuracy, RTW computed two independent ways as a cross-check, cluster bootstrap over
task IDs with BCa intervals, TOST equivalence testing for H4, Holm correction across
the primary family, and a fixed decision table mapping outcomes to
supported/refuted/inconclusive before any confirmatory run.

---

## What broke, and how it was caught

This section exists because the failures are more informative than the successes,
and because every one of them was caught by a check built *before* it was needed.

**A boolean inversion that would have flipped every accuracy conclusion.**
`patsy`/`statsmodels` silently treats a boolean outcome column as a two-level
categorical and fits the wrong reference level. A synthetic dataset with a planted
true P(success) = 0.80 came back fitted at **0.20** — an exact inversion. Caught only
because the analysis pipeline was validated against data with known answers before
touching real results. Fixed by explicit integer coercion, documented in the code so
it cannot silently regress.

**An RTW metric that wasn't measuring the pre-registered quantity.**
The GLM path computed tokens per *attempt*; the spec's primary outcome is tokens per
*success*. The two agreed perfectly in cells where accuracy happened to match between
arms and diverged by over 100 percentage points where it didn't. Caught by the
deliberate decision to compute RTW two independent ways — the cross-check existed
precisely so a modeling artifact couldn't pass unnoticed, and it earned its place on
the first real run.

**Two more statistical defects**: the negative-binomial dispersion parameter was
silently fixed at 1.0 rather than estimated, and the model produced a confident-looking
RTW from a cell with zero successes (perfect separation, warned about on stderr where
it's easy to miss). Both now detected and surfaced.

**In-prompt tool protocols are not portable.** The harness deliberately delivers tool
schemas in-prompt rather than via provider tool-calling APIs, so that the Schema factor
is a pure token intervention. On Groq, `gpt-oss-120b` ignores that protocol and emits a
**native function call**, which the provider validates server-side and rejects with a
400 — no usage data returned, so the attempt can't even be counted. Adding an explicit
prohibition made it worse: the request succeeded, consumed 370 output tokens, and
returned **empty content**. This is worth knowing for anyone building cross-provider
agent evaluations.

**A power analysis that measured the wrong variance.** The pilot estimated the sample
size needed to detect *token* differences and concluded n = 13–39 would do. But the
primary metric is tokens per *success*, which inherits accuracy variance through its
denominator. With this model's low, unstable accuracy, that denominator destroys
precision — which is why two of four confidence intervals span zero at n = 53. The
study isn't underpowered for what the pilot measured; it's underpowered for what the
spec actually asks.

---

## Limitations

Stated plainly, because they bound what the results support.

- **The pre-registration is a good-faith freeze, not a timestamped one.** The analysis
  plan and code were written and hashed before the confirmatory run, but the git
  repository wasn't initialized until afterward, so the tag proving the ordering was
  applied retroactively. The freeze is real; the cryptographic proof of it is not.
- **Underpowered for the primary metric** (see above). Point estimates are large;
  intervals are wide. Only two of four cells are distinguishable from zero.
- **Multi-turn transfer was not testable.** BFCL attempts averaged ~94,000 tokens
  each; against a 100,000-token daily free-tier cap, the 208-attempt arm would need
  roughly 97 days. Single-turn transfer was tested; agentic transfer was not.
- **M2 uses a different model than pre-registered.** `llama-3.3-70b-versatile`
  replaced `gpt-oss-120b` after the protocol incompatibility above. The substitution
  is evidence-based and required no prompt change (so the arms remain comparable),
  but it is a deviation.
- **One model family per scale.** "Small models break, large models absorb" rests on
  two models. It's a hypothesis worth testing properly, not an established result.

---

## Reproducing

```bash
pip install -r requirements.txt          # mlx-lm, statsmodels, scipy, pandas, groq

# verify the suite's ground truth before any run
python -m prism.analysis.verify_suite prism/suite/w2_staging/gsm8k_extracted.json

# prove the multi-turn harness on your machine
python prism/scripts/smoke_test_bfcl.py

# the confirmatory run (local, ~hours)
python run_pilot.py --model mlx \
  --tasks prism/suite/w2_staging/full_suite_n53.json --seeds 2

# analysis
python prism/scripts/run_confirmatory_analysis.py results/<run>.jsonl
```

Interrupted runs resume without redoing completed work:
`--resume results/<run>.jsonl`. Resume is verified against a simulated mid-attempt
crash — the case where turn records exist but the summary never landed — and produces
outcomes byte-identical to an uninterrupted run.

---

## Repository layout

```
prism/harness/       instrument: model adapters, runners, append-only accounting
prism/analysis/      bootstrap + GLM + confirmatory pipeline (hash-pinned)
prism/scripts/       extraction, verification, probes, localization tooling
prism/suite/         the task suite (EN + PT) and its provenance
prism/vendor/        BFCL's own simulator, vendored (Apache 2.0, one disclosed patch)
results/             every run, append-only, with manifests
PRISM_SPEC.md        full design, statistical plan, and the audit trail of what changed
```

`PRISM_SPEC.md` Appendix B is the honest record: every design decision that was
revised, why, and what evidence forced it — including the two compiler revisions, the
sample-size reduction from 80 to 53, and a third candidate fix that was tested and
deliberately **not** applied because it didn't work.

---

## What I'd do differently

- **Run the power analysis on the actual primary metric**, not a proxy for it. This
  is the one mistake that materially limits what the results can claim.
- **Initialize the repository before writing any code.** The pre-registration was
  written in good faith and hashed on time; the proof of that ordering was lost to
  an assumption that a `git init` had already happened.
- **Probe every provider's protocol compatibility on day one**, not at the point of
  use. The in-prompt/native tool-call incompatibility was discoverable in five
  requests and instead surfaced after the arm was designed around it.
- **Check per-attempt token cost against quota limits before designing an arm.**
  The multi-turn transfer arm was infeasible from the start — ~94k tokens per
  attempt against a 100k daily cap — and one arithmetic check would have shown it.

The recurring theme: every one of these was cheap to check early and expensive to
discover late. The checks that *were* built early — ground-truth verification,
dual-computed RTW, synthetic-recovery tests for the analysis code — each caught a
defect that would otherwise have reached a conclusion.
