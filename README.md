# Prism — The Token Taxes

**Three popular techniques for cutting LLM costs. Applied together, measured properly.
On a small model, they roughly doubled the cost of getting work actually done.**

A pre-registered 2×2×2 factorial experiment. 848 runs on a local 3B model, plus a
transfer check on a 70B model. Full harness, statistical pipeline, append-only
results, and an honest audit trail of everything that broke.

---

## The short version

Running large language models costs money per **token** — roughly, per word in and
per word out. So a large industry of advice has grown up around using fewer tokens:
compress the tool descriptions you send the model, cap how much it's allowed to think
out loud, watch out for languages that encode less efficiently.

Each of those saves tokens. That part is easy to verify and generally true.

The question nobody was answering: **does saving tokens actually save money?**

It sounds like the same question. It isn't — and the gap between them is where this
experiment lives.

---

## Why "fewer tokens" isn't the same as "cheaper"

Think about a factory making a physical part.

Someone finds a way to use 30% less material per unit. Real saving, easy to measure,
shows up immediately on the materials invoice. Then quality control starts rejecting
more parts, because thinner ones crack. You're now producing more units, scrapping
more of them, and paying for every scrapped one.

Your cost per unit *produced* went down. Your cost per unit *shipped* went up.

The materials saving was real. It was also a false economy.

LLM workloads have exactly this structure, and it's rarely measured this way. A failed
task still costs full price — you paid for every token the model spent getting the
wrong answer. So the number that determines your actual bill isn't tokens per call.
It's:

> ### tokens per *successful* task
> *(all tokens spent, including on failures, divided by the tasks that actually
> completed)*

That's the primary metric of this study. Everything else follows from taking it
seriously.

---

## What the experiment found

### 1. On a small model, the optimizations backfired — badly

Qwen2.5-3B, 848 runs across 53 tasks:

| Workload | Language | Cost per completed task | Success rate (before → after) | Verdict |
|---|---|---|---|---|
| Math + tools | English | **2.1× higher** | 31.3% → 16.2% | worse |
| Math + tools | Portuguese | 1.2× higher | 23.8% → 21.3% | worse |
| Multi-step agent | English | **2.0× higher** | 15.4% → 3.8% | worse |
| Multi-step agent | Portuguese | 0.7× (a real saving) | 7.7% → 7.7% | better, but fragile |

Three of four arms got **more expensive per completed task**. In English the cause is
stark: success rates roughly halved, so the token savings were swamped by paying for
twice as many failures. In one of four arms the savings survived — but that cell rests
on two successful runs per condition, which is too thin to lean on.

**In plain terms:** if this workload was costing you $1,000/month, the "optimized"
version costs about $2,100/month for the same amount of finished work.

### 2. …but the damage doesn't transfer to a larger model

The same interventions on Llama-3.3-70B, 106 runs across the same task family:

| Language | RTW | 95% BCa CI | Accuracy off → on | Gate |
|---|---|---|---|---|
| EN | +11.6% | (−19.9%, +30.9%) | 92.3% → 91.7% | **passes** |
| PT | +15.3% | (−10.3%, +50.1%) | 92.9% → 100.0% | **passes** |

The accuracy penalty is simply gone. Where the 3B model lost half its successes, the
70B model loses 0.6 percentage points — and in Portuguese it goes up.

**A control for the obvious objection.** M1's headline covers 40 tasks; M2 covers
seven, so the difference could be task difficulty rather than model scale. Re-running
M1's analysis restricted to *exactly the seven tasks M2 saw* settles it — and the
effect gets **stronger**, not weaker:

| Same 7 tasks | Qwen-3B | Llama-70B |
|---|---|---|
| EN accuracy off → on | 50.0% → **14.3%** | 92.3% → **91.7%** |
| EN cost per success | 3,043 → 15,123 (**5.0× worse**) | 2,200 → 1,946 |
| PT accuracy off → on | 35.7% → **14.3%** | 92.9% → **100%** |
| PT cost per success | 4,185 → 10,782 (**2.6× worse**) | 2,195 → 1,859 |

Same tasks, same schemas, same protocol — opposite outcomes. The collapse tracks
model capacity, not the tasks.

**What this does and doesn't establish.** Both M2 intervals span zero, so the
*magnitude* of the saving is not demonstrated: "12–15% cheaper on a large model" is
not a claim this data supports. What it does support is the qualitative difference —
the interventions are **harmful on the small model and harmless on the large one**,
and the accuracy gate flips from failing to passing. A penalty disappearing is not
the same as a benefit appearing, and only the first is established here.

**The practical takeaway:** "small cheap model + aggressive token compression" is the
worst of both worlds — you pay the compression's accuracy cost precisely where the
model can least afford it. On capable models the same compression appears safe, which
is a weaker and more useful claim than "it pays off."

### 3. Two techniques that are each survivable become fatal together

One task, isolated across five independent random seeds:

| Condition | Success |
|---|---|
| Full instructions, any thinking budget | **10 / 10** |
| Compressed instructions, unlimited thinking | 3 / 5 |
| Compressed instructions **and** capped thinking | **0 / 5** |

Neither factor alone reliably breaks the task. The combination reliably does.

This is direct evidence against the assumption that these savings simply add up — the
central hypothesis this experiment was built to test. The reality is worse than
sub-additive: the interaction is actively destructive.

I tested whether this was my own compression tool's fault by restoring the specific
sentence it had trimmed. **It didn't help** (still 3/5). That killed the convenient
explanation and left the interaction standing as real, so the tool was frozen instead
of tuned further. Continuing to patch it would have amounted to engineering away the
finding.

### 4. The language effect is real, but it doesn't have a direction

Three tasks showed complete, seed-stable splits between English and Portuguese — and
they don't point the same way:

- One task: **Portuguese succeeds 5/5, English fails 5/5.** The English run invents a
  multiplication that appears nowhere in the problem.
- Another: the exact reverse. Portuguese drops a dimension of a 2-D problem.
- A third: Portuguese fails uniformly; English depends on the other two factors.

A native speaker reviewed all three translations and approved them unchanged. The
failures are in model comprehension, not translation quality. So this argues against a
simple "non-English tax" and toward **task-specific comprehension failures that can
land on either language** — including, in one case, on English.

This finding is why the localization protocol changed mid-project: from
back-translation review (which cannot detect this, since the translations are correct)
to running the model in both languages and comparing outcomes directly.

---

## How it was measured

### The pipeline end to end

Every stage below is a gate: nothing reaches the next box unverified, and nothing that
fails the last one gets reported as a saving.

<p align="center">
  <img src="docs/prism_architecture.png" alt="Prism experimental pipeline: public datasets feed suite construction, which feeds execution, which feeds analysis, which ends at a non-inferiority gate deciding whether a saving is claimable" width="100%">
</p>

The two properties worth noticing: **ground truth is derived and independently
re-verified rather than hand-written**, and **the accuracy gate sits between the
measurement and the claim** — which is exactly why three of four arms in this study
produce no claim at all.

### Design

A **2×2×2 within-task factorial**. Every task runs through all eight combinations, so
each task acts as its own control — the standard defence against tasks simply differing
in difficulty.

| Factor | Off | On | The claim being tested |
|---|---|---|---|
| **S** — Structure | Raw JSON tool schemas | Compressed schemas | Schema prose is mostly filler |
| **B** — Budget | Unconstrained reasoning | Capped output budget | Models over-explain |
| **L** — Language | English user content | Portuguese user content | Non-English inflates token counts |

**Hypotheses.** H1–H3: each factor reduces tokens per success without an accuracy
penalty beyond δ = 3pp. **H4: the three effects are additive** — the combined saving
equals the sum of the parts. H4 is the novel one; it's also the one the data most
clearly refutes.

**The non-inferiority gate.** A saving is only claimable if accuracy in the "on"
condition stays within 3 percentage points of "off". Otherwise the result is reported
as a frontier point, not a win. This gate is what converts "we saved tokens" into "we
saved money", and it's what blocks the claim in both English arms.

### Models

- **M1 (core)** — Qwen2.5-3B-Instruct-4bit, local via MLX. 53 tasks × 8 cells × 2 seeds
  = **848 runs**. Exact tokenizer counts.
- **M2 (transfer)** — Llama-3.3-70B-Versatile via Groq, single seed. Token counts from
  API usage fields only.

### Task suite (n = 53)

Both sources machine-verified rather than hand-written — a deliberate constraint after
hand-typed ground truth caused a false test failure during the pilot.

- **40 GSM8K-hard** items (≥ 3 reasoning steps) wrapped with calculator and lookup
  tools. Ground truth is auto-derived by chaining GSM8K's own `<<expr=result>>`
  annotations, then independently re-verified by a separate script. 69 candidates
  yielded 40 acceptances; **29 were dropped as unverifiable rather than guessed at.**
- **13 BFCL-v4 multi-turn** agent tasks (single-simulator-class only). Graded by
  **state comparison** against BFCL's own vendored simulator — the same methodology
  BFCL's evaluation harness uses internally — rather than by matching call strings,
  which would wrongly fail equally-valid alternate orderings.

Tool schemas are delivered **in-prompt**, never through the provider's native
tool-calling API, so the Structure factor stays a pure token intervention that behaves
identically across backends. This decision has consequences — see below.

### Inside a single run

<p align="center">
  <img src="docs/prism_run_loop.png" alt="Inside a single run: the system prompt and tool schemas produce a model reply, which is parsed into a tool call, a final answer, or a logged protocol violation" width="92%">
</p>

The **Structure** factor changes only the schemas in the first box. The **Budget**
factor caps how much the model may emit per reply. Everything else is held identical,
which is what makes the comparison a clean one.

Note the third branch: when the model breaks the protocol, that's **logged and left
alone**, never silently repaired. Quietly fixing malformed replies would hide exactly
the failure mode compression is suspected of causing — so the violation rate is treated
as data, not as noise to clean up.

### Statistics

- Negative-binomial GLM for tokens, logistic GLM for accuracy, full S×B×L factorial
- Every confidence interval from a **cluster bootstrap** resampling task IDs — never
  individual rows, which would break the pairing the design depends on — with BCa
  correction. Coverage validated at 95.0% against a 95% nominal target over 200
  simulated datasets.
- **TOST equivalence test** for H4, so "the effects are additive" has to be positively
  demonstrated rather than inferred from a failure to reject
- Holm correction across H1–H4; Benjamini-Hochberg on the exploratory family, reported
  in a separate table
- RTW computed **two independent ways** (model-marginal and direct paired) as a
  cross-check against modelling artefacts. This caught a real defect — see below.
- Cell execution order randomized per task, deterministically seeded for
  reproducibility

### The full technical numbers

**M1 — Qwen2.5-3B, 848 runs (40 GSM8K + 13 BFCL tasks, 2 seeds)**

| Suite · language | RTW | 95% BCa CI | Accuracy off → on | Claimable? |
|---|---|---|---|---|
| GSM8K · EN | −109.7% | (−336.6%, −3.2%) | 31.3% → 16.2% | **no** — gate failed |
| GSM8K · PT | −22.0% | (−163.2%, +33.9%) | 23.8% → 21.3% | gate passed, CI spans zero |
| BFCL · EN | −102.2% | (−637.6%, +14.2%) | 15.4% → 3.8% | **no** — gate failed |
| BFCL · PT | +28.8% | (+5.0%, +47.9%) | 7.7% → 7.7% | yes — on 2 successes/arm |

**M2 — Llama-3.3-70B, 106 runs (7 GSM8K tasks, repeated calls)**

| Suite · language | RTW | 95% BCa CI | Accuracy off → on | Claimable? |
|---|---|---|---|---|
| GSM8K · EN | +11.6% | (−19.9%, +30.9%) | 92.3% → 91.7% | gate passed, CI spans zero |
| GSM8K · PT | +15.3% | (−10.3%, +50.1%) | 92.9% → 100.0% | gate passed, CI spans zero |

RTW ("recoverable token waste") = `1 − T_on/T_off`, where T is all-in tokens per
success. Negative means the optimized condition costs **more** per completed task.

M2's two measurements per cell are **repeated calls at temperature 0.2, not seed
replicates** — Groq exposes no sampling seed, so `seed_effective` is recorded as
`None` throughout. They are independent draws, but calling them "seeds" would be
wrong.

Note the interval widths. GSM8K · PT, the largest arm at 640 runs, spans −163% to
+34% — **genuinely inconclusive**, not a demonstrated negative. That's a real
limitation of this study, diagnosed below rather than glossed over.

---

## What broke, and how it was caught

This section exists because the failures are more informative than the successes, and
because each was caught by a check built *before* it was needed.

**A boolean inversion that would have flipped every accuracy conclusion.**
`patsy`/`statsmodels` silently treats a boolean outcome column as a two-level
categorical and fits the wrong reference level. A synthetic dataset with a planted true
success rate of 0.80 came back fitted at **0.20** — an exact inversion. Every
accuracy-gate verdict would have been backwards. Caught only because the analysis
pipeline was validated against data with *known* answers before touching real results.
Fixed by explicit integer coercion, documented in the code so it can't silently
regress.

**A primary metric that wasn't measuring the pre-registered quantity.** The
model-marginal path computed tokens per *attempt*; the specification's primary outcome
is tokens per *success*. The two agreed perfectly in cells where accuracy happened to
match across conditions, and diverged by **over 100 percentage points** where it
didn't. Caught by the deliberate choice to compute the headline number two independent
ways — the cross-check existed precisely so a modelling artefact couldn't pass
unnoticed, and it earned its place on the first real run.

**Two further statistical defects**, both found by the same synthetic-recovery
approach: the negative-binomial dispersion parameter was silently fixed at 1.0 rather
than estimated, and the model produced a confident-looking result from a cell with zero
successes (perfect separation, warned about on `stderr` where it's easy to miss). Both
now detected and surfaced explicitly.

**In-prompt tool protocols are not portable across providers.** On Groq,
`gpt-oss-120b` ignores an in-prompt JSON protocol and emits a **native function call**,
which the provider validates server-side and rejects with a 400 — no usage data
returned, so the attempt can't even be counted. Adding an explicit "do not use function
calling" instruction made it worse: the request succeeded, consumed 370 output tokens,
and returned **empty content**. Llama-3.3-70B follows the same protocol perfectly with
no prompt changes at all. Worth knowing for anyone building cross-provider agent
evaluations.

**A resume that silently re-ran everything it claimed to skip.** Long runs can be
interrupted by an API quota, so the harness supports `--resume`. It was tested
against an interruption and against the harder case of a crash landing *mid-attempt*
— and it passed both. It was never tested against a **seedless provider**. Groq
exposes no sampling seed, so the runner records `seed_effective=None`, while the
resume built its lookup key from the raw loop variable `0`. `(task, cell, None)` never
matches `(task, cell, 0)`, so a resumed run cheerfully printed "53 combos already
have a real outcome, will be skipped" and then re-executed all 53. One root cause,
three separate symptoms, and **only the first was visible from the console**:

1. cells re-running instead of being skipped — a wasted day of API quota
2. the re-runs written as `attempt=1` again, colliding with the originals and
   producing duplicate keys
3. orphaned turn records from an earlier aborted run silently inflating the token
   total of the attempt that followed them, because orphan-backfilling keys on
   `seed_effective` too and had been defeated the same way

Symptoms 2 and 3 were caught only because the accounting layer cross-checks each
attempt's summary against the sum of its own turn records and refuses to proceed when
they disagree. The recovery script (`scripts/repair_duplicate_attempts.py`)
renumbers repeated attempts and splits orphans back out by reconciling token sums —
turning the damage into extra replicates rather than discarding it, since the re-runs
are genuine independent measurements.

The generalisable lesson is not "test resume." It is that a mock which is more
convenient than the real dependency will quietly skip the code path the real
dependency exercises.


**Rate limits need pacing, not retries.** Reacting to HTTP 429s is useless when the
binding constraint is a tokens-per-minute ceiling. The harness now paces proactively
against a rolling 60-second budget, honours the API's own `retry-after` value, and
distinguishes a transient throttle from an exhausted daily quota so it stops cleanly
instead of generating hundreds of error rows over hours.

**A power analysis that measured the wrong variance.** The pilot estimated the sample
size needed to detect *token* differences and concluded n = 13–39 would suffice. But
the primary metric is tokens per *success*, which inherits accuracy variance through
its denominator. With this model's low, unstable accuracy, that denominator destroys
precision — which is why two of four intervals span zero at n = 53. The study isn't
underpowered for what the pilot measured; it's underpowered for what the specification
actually asks. **This is the single most important methodological lesson here.**

---

## Audited afterwards

A follow-up study, [Tolerance](https://github.com/hugocorreia123/tolerance-agent-evals),
re-examined whether this study could detect what it claimed. It found the minimum
detectable effect for the GSM8K arm to be 121–222%, meaning **the −109.7% headline sits
below this study's own detection threshold** — and that the formula producing that
threshold is itself optimistic by 1.7–3.7×. The direction of the finding is supported by
the matched-task control; the magnitude is not resolvable at n=53. That audit is linked
here rather than buried, because it materially qualifies what follows.

## Limitations

Stated plainly, because they bound what the results support.

- **Underpowered for the primary metric** (above). Point estimates are large; intervals
  are wide. Only two of four cells are distinguishable from zero.
- **The pre-registration is a good-faith freeze, not a timestamped one.** The analysis
  plan and code were written and hashed before the confirmatory run, but the git
  repository wasn't initialized until afterward, so the `prereg-v1` tag was applied
  retroactively. The freeze is real; cryptographic proof of the ordering is not. The
  hash at freeze was `e584de6214e3db4e`; after the tokens-per-success correction it is
  `27ee26977f34a714` — that correction aligned the code with the written plan rather
  than changing the plan.
- **Multi-turn transfer was not testable.** BFCL runs average ~94,000 tokens each;
  against a 100,000-token daily free-tier cap, the 208-run arm would need ~97 days.
  Single-turn transfer was tested; agentic transfer was not.
- **n = 53, not the planned 80.** BFCL's variant files each confound a different
  capability with the S/B factors, so they were excluded rather than mixed in
  uninspected; padding with more GSM8K would have erased the multi-turn diversity the
  split exists for.
- **M2 uses a different model than pre-registered.** `llama-3.3-70b-versatile` replaced
  `gpt-oss-120b` after the protocol incompatibility above. Evidence-based, and it
  required no prompt change so the arms stay comparable — but it is a deviation.
- **M2 is quota-shaped, not design-shaped.** Seven tasks and two repeated calls per
  cell (106 runs) is what a free-tier daily token cap allowed across three days, not a
  chosen sample size. Both its intervals span zero, so M2 establishes that the
  accuracy penalty *disappears* at 70B — not that a token saving *appears*.
- **One model family per scale.** "Small models break, large models absorb" rests on
  two models. It is a hypothesis worth testing properly, not an established result.

---

## Reproducing

```bash
pip install -r requirements.txt

# verify ground truth before any run — a mandatory gate
python -m prism.analysis.verify_suite prism/suite/w2_staging/gsm8k_extracted.json

# prove the multi-turn harness works on this machine
python prism/scripts/smoke_test_bfcl.py

# the core run: 848 attempts, local, several hours
python run_pilot.py --model mlx \
  --tasks prism/suite/w2_staging/full_suite_n53.json --seeds 2

# transfer check (needs GROQ_API_KEY; stops cleanly at the daily quota)
python run_pilot.py --model groq --model-id llama-3.3-70b-versatile \
  --tasks prism/suite/w2_staging/gsm8k_extracted.json --limit 12 --seeds 1

# analysis
python prism/scripts/run_confirmatory_analysis.py "$(ls -t results/*.jsonl | head -1)"
```

Interrupted runs resume without redoing completed work: `--resume results/<run>.jsonl`.
Resume is verified against a simulated mid-attempt crash — the hard case, where turn
records exist but the summary never landed — and produces outcomes byte-identical to an
uninterrupted run. Partial attempts are backfilled as `harness_error` so their spent
tokens stay accounted for rather than vanishing.

The compression/safety tradeoff reproduces with
`python prism/scripts/audit_compiler.py`.

---

## Repository layout

```
prism/harness/       instrument: model adapters, runners, append-only accounting
prism/analysis/      bootstrap + BCa, GLMs, confirmatory pipeline (hash-pinned)
prism/scripts/       extraction, verification, probes, localization tooling
prism/suite/         the 53-task suite (EN + PT) and its provenance
prism/vendor/        BFCL's own simulator, vendored (Apache 2.0, one disclosed patch)
results/             every run, append-only, with manifests
PRISM_SPEC.md        full design, statistical plan, and the audit trail
```

Every result file is append-only with a hash-pinned manifest recording the suite,
config, and code version that produced it. Token counts come only from API usage fields
or exact tokenizer counts; mock runs are flagged non-confirmatory and excluded from
analysis.

`PRISM_SPEC.md` Appendix B is the honest record: every design decision that was revised,
why, and what evidence forced it — including two compiler revisions, the sample-size
reduction from 80 to 53, and a third candidate fix that was tested and deliberately
**not** applied because it didn't work.

---

## What I'd do differently

- **Run the power analysis on the actual primary metric**, not a proxy for it. This is
  the one mistake that materially limits what these results can claim.
- **Initialize the repository before writing a line of code.** The pre-registration was
  written in good faith and hashed on time; the proof of that ordering was lost to an
  assumption that a `git init` had already happened.
- **Probe every provider's protocol compatibility on day one**, not at the point of
  use. The tool-call incompatibility was discoverable in five requests and instead
  surfaced after an entire arm had been designed around it.
- **Check per-run token cost against quota limits before designing an arm.** The
  multi-turn transfer arm was infeasible from the start — ~94k tokens per run against a
  100k daily cap — and one piece of arithmetic would have shown it.
- **Test against the awkward dependency, not the convenient mock.** Resume was tested
  twice, thoroughly, against a mock that wasn't seedless — so it never exercised the
  one property the real provider has. The mock agreed with the code instead of
  challenging it.

Sorted by *how* they failed rather than what they were, these fall into two groups
that need completely different defences.

**Failures that announce themselves.** The protocol incompatibility returned an HTTP
400. The infeasible arm returned 429s. Both were unmissable the moment the code ran
against the real dependency — the error was designing an entire arm *before* spending
the five requests that would have exposed it. These cost time, not correctness, and
the defence is trivial: run the smallest real thing first.

**Failures that return a plausible number.** These are the dangerous ones, and nothing
about them looks wrong. An accuracy model that returns 0.20 when the truth is 0.80
doesn't crash — it produces a clean table with every conclusion inverted. A metric
computing tokens per *attempt* instead of per *success* agrees with the correct version
in every cell where accuracy happens to match, so it looks right most of the time.
Duplicate run records just make a token total slightly larger. A resume that skips
nothing still prints "53 combos already have a real outcome, will be skipped."

Only one thing catches that class: **a second, independent computation of something
the code already believed.**

| Silent defect | The independent second opinion that caught it |
|---|---|
| Hand-typed ground truth | re-derived from the dataset's own annotations |
| A misspecified headline metric | the same quantity computed a second way |
| An inverted accuracy model | synthetic data with a known correct answer |
| Duplicate and orphaned run records | each attempt's summary vs. the sum of its own turns |

The two silent defects that were *not* caught are exactly the two where no second
computation existed: the power analysis had no independent estimate to disagree with
it, and nothing ever verified that the pre-registration commit was real.

"Independent" carries the weight there. A second computation that shares the first's
assumptions confirms them rather than testing them — the dual-metric check worked
precisely because one path ran through a GLM and the other was raw arithmetic over the
records, so an error in either had nowhere to hide. A single computation, however
careful, has nothing to be wrong against.

---

## Part of a series

Three studies applying the same discipline to questions practitioners answer by
folklore:

- [**Prism**](https://github.com/hugocorreia123/prism-token-taxes) — do LLM token-saving techniques actually save money?
- [**Tolerance**](https://github.com/hugocorreia123/tolerance-agent-evals) — could your evaluation detect the improvement you claim? (It audits Prism, and finds Prism's headline sits below its own detection threshold.)
- [**Tripwire**](https://github.com/hugocorreia123/tripwire-drift-economics) — is a drift alarm worth more than a cron job?

Each reports what it found, including when that was nothing.
