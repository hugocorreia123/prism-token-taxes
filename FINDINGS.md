# Prism — The Token Taxes

## Findings

**A pre-registered factorial study of whether the standard techniques for reducing
LLM token spend actually reduce cost.**

Hugo Correia · July 2026 · [github.com/hugocorreia123/prism-token-taxes](https://github.com/hugocorreia123/prism-token-taxes)

---

## Abstract

Three widely-recommended techniques for cutting LLM token consumption — compressing
tool schemas, capping reasoning length, and accounting for non-English token
inflation — were applied together in a 2×2×2 within-task factorial design and
measured against **all-in tokens per successful task**, a metric that charges failed
attempts to the cost of the successes.

On a 3-billion-parameter model (848 runs, 53 tasks), the combined intervention made
work **more expensive, not less**: English accuracy fell from 31.3% to 16.2%, and cost
per completed task roughly doubled. Three of four measured arms failed a
pre-specified non-inferiority gate and were therefore not claimable as savings at all.

On a 70-billion-parameter model (106 runs), the same interventions applied to the same
tasks cost **no measurable accuracy** (92.3% → 91.7%). A matched-task control confirms
this is a property of model scale rather than task difficulty: restricted to the
identical seven tasks, the small model performs *worse* than on the full suite, not
better.

The study additionally isolates a **Schema × Budget interaction** in which two
individually survivable interventions become jointly fatal, and documents language
effects that are large, seed-stable, and — contrary to the usual assumption —
**not directionally consistent**.

The central practical finding is asymmetric: the accuracy penalty demonstrably
disappears with scale, but a token saving appearing at scale is **not** established;
both large-model intervals span zero.

---

## 1. The question

Large language models are billed per token. A substantial body of practitioner advice
has grown around consuming fewer of them: strip verbose tool descriptions, constrain
how much the model reasons out loud, prefer languages that tokenize efficiently.

Each of these does reduce token counts. That part is easy to verify and generally
true.

The question this study asks is different, and it is rarely asked:

> **Does reducing tokens reduce cost?**

These sound identical. They are not, and the gap between them is where the entire
result lives.

---

## 2. Theory: why "fewer tokens" is not "cheaper"

### 2.1 The yield problem

Consider a factory producing a physical component. An engineer finds a way to use 30%
less material per unit — a real, immediately measurable saving on the materials
invoice. Some weeks later, quality control begins rejecting more units, because the
thinner components crack under load.

Cost per unit *produced* has fallen. Cost per unit *shipped* has risen. The material
saving was real; it was also a false economy, and the accounting that reported it as a
success was measuring the wrong denominator.

LLM workloads have exactly this structure. A failed task is not free: the tokens spent
arriving at a wrong answer are billed at the same rate as the tokens spent arriving at
a right one. Any optimization that reduces per-call token consumption while reducing
success rate is trading a visible saving against an invisible cost.

### 2.2 The metric that follows

The quantity that determines an actual bill is therefore not tokens per call. It is:

> **All-in tokens per successful task** — every token spent across every attempt,
> including attempts that failed, divided by the number of tasks that actually
> completed.

Formally, for a condition *c*:

```
T_c  =  Σ (tokens_in + tokens_out)  /  Σ successes
        over all attempts in c          in c
```

The study reports **Recoverable Token Waste**:

```
RTW  =  1 − T_on / T_off
```

where *on* is the fully-optimized condition and *off* is the baseline. RTW is positive
when the optimization genuinely reduces the cost of completing work, and **negative
when it increases it** — a possibility the per-call framing cannot express.

### 2.3 The non-inferiority gate

A token reduction accompanied by an accuracy collapse is not an efficiency result; it
is a different operating point on a quality/cost curve. To keep those apart, an RTW
figure is **claimable only if accuracy in the optimized condition remains within
δ = 3 percentage points of baseline**. Otherwise the result is reported as a frontier
point — an honest description of a tradeoff — and not as a saving.

This gate is what converts "we used fewer tokens" into "we spent less money," and it
is where most of this study's arms fail.

### 2.4 The additivity assumption

Each of the three techniques is normally evaluated alone. Practitioners applying two
or three of them implicitly assume the savings compose: if compression saves 20% and
budgeting saves 20%, the pair is expected to save somewhere near 36%.

That assumption is untested, and it is the novel component of this design. Three
outcomes are possible:

- **Additive** — effects combine as expected
- **Sub-additive** — combined saving is less than the sum (overlapping mechanisms)
- **Interactive** — the combination behaves qualitatively unlike either part

The last case is the interesting one, and it is what the data shows.

---

## 3. Hypotheses

| | Statement |
|---|---|
| **H1** | Compressed tool schemas reduce tokens per success without an accuracy penalty exceeding δ = 3pp |
| **H2** | Budgeted reasoning reduces tokens per success without an accuracy penalty exceeding δ = 3pp |
| **H3** | The Portuguese token premium is partly tokenizer inefficiency and partly model competence, and the two components are separable |
| **H4** | The three effects are **additive** — the combined RTW equals the sum of the individual RTWs |

All four were specified before the confirmatory run, together with the analysis
procedure and a decision table mapping every possible outcome pattern to
supported / refuted / inconclusive.

---

## 4. Method

### 4.1 Design

A **2×2×2 within-task factorial**. Every task is executed under all eight combinations
of the three binary factors, so each task serves as its own control — the standard
defence against confounding by task difficulty.

| Factor | Off (0) | On (1) |
|---|---|---|
| **S** — Structure | Raw JSON tool schemas | Compressed schemas (compiler v1.2) |
| **B** — Budget | Unconstrained output | Capped output budget per reply |
| **L** — Language | English user content | Portuguese user content |

Schemas and system prompts remain in English in every cell. Only user-facing task
content is localized, so the Language factor measures what a Portuguese-speaking user
would actually experience rather than a fully-translated system.

Cell execution order is randomized per task with a deterministic seed, guarding
against drift in server load or thermal throttling over a long run.

### 4.2 The intervention, precisely

**Structure (S).** Tool schemas are delivered **in the prompt**, never through a
provider's native tool-calling API, so that compression is a pure token intervention
that behaves identically across model backends. The compressor (frozen at v1.2)
preserves tool names, parameter names, types, `required` lists and enum values
byte-for-byte — the contract the model must reproduce — and compresses only prose.
Two clause categories are never removed regardless of length: **deontic constraints**
("must", "cannot", "only if") and **purposive guidance** ("instead of", "to avoid").
Measured compression across the 20 real schemas in the suite: **47%**, down from 58%
before those protections were added. The difference is the disclosed cost of not
silently dropping load-bearing text.

**Budget (B).** A cap on tokens emitted per model reply. Attempts truncated at the cap
are recorded as failures with their tokens retained in the numerator — truncation is a
real cost, not a discarded observation.

**Language (L).** Task content translated to European Portuguese via machine
translation followed by native-speaker review. Of 53 drafts, **0% required
correction** — a result consistent with the language findings in §5.5, where faithful
translations still produced large accuracy differences.

### 4.3 Task suite (n = 53)

Both sources are machine-verified rather than hand-written, following a pilot incident
in which hand-typed ground truth caused a false test failure.

**40 GSM8K-hard items** (≥ 3 reasoning steps), wrapped with a calculator and a lookup
tool. Ground truth is derived by chaining GSM8K's own `<<expr=result>>` calculator
annotations into a single expression, evaluated with the same safe evaluator the
calculator tool uses, and independently re-verified by a separate script before any
run. Of 69 candidates meeting the step threshold, **40 were accepted and 29 rejected
as unverifiable** — dropped rather than guessed at.

**13 BFCL-v4 multi-turn agent tasks**, restricted to those using a single simulator
class. Grading is by **state comparison** against BFCL's own vendored simulator — the
methodology BFCL's evaluation harness uses internally — rather than by matching call
strings, which would incorrectly fail equally-valid alternative orderings. All 13
ground-truth trajectories replay against that simulator with zero execution errors
before acceptance.

The remaining 187 BFCL base tasks combine multiple simulator classes and were excluded
rather than integrated without review. The planned suite size was 80; the disclosed
reduction to 53 is discussed in §7.

### 4.4 Models

| Arm | Model | Runs | Token source |
|---|---|---|---|
| **M1** (core) | Qwen2.5-3B-Instruct-4bit, local via MLX | 53 tasks × 8 cells × 2 seeds = **848** | exact tokenizer counts |
| **M2** (transfer) | Llama-3.3-70B-Versatile via Groq | 7 tasks × 8 cells × ~2 calls = **106** | API usage fields only |

M2's two measurements per cell are **repeated calls at temperature 0.2, not seed
replicates** — the provider exposes no sampling seed, and `seed_effective` is recorded
as `None` throughout. They are independent draws; describing them as "seeds" would be
incorrect.

### 4.5 Statistical specification

- **Token model:** negative-binomial GLM, full S×B×L factorial, dispersion parameter
  estimated by maximum likelihood (not fixed).
- **Accuracy model:** logistic GLM, same factorial structure.
- **Intervals:** all confidence intervals come from a **cluster bootstrap that
  resamples task identifiers**, never individual rows — resampling rows would destroy
  the pairing the within-task design depends on. Bias-corrected and accelerated (BCa)
  correction applied. Coverage of the implementation was validated at **95.0% against a
  95% nominal target over 200 simulated datasets** before use.
- **RTW is computed two independent ways** — once as a GLM marginal contrast, once as
  a direct paired ratio over the raw records — as a cross-check against modelling
  artefacts. Their agreement is itself evidence; their disagreement caught a real
  defect (§8).
- **H4** is tested by a **TOST equivalence procedure**, so additivity must be
  positively demonstrated rather than inferred from a failure to detect an
  interaction.
- **Multiplicity:** Holm correction across H1–H4; Benjamini–Hochberg on the
  exploratory family, reported separately.
- **Exclusions:** harness errors are reported and excluded; refusals count as failures;
  cap-truncations count as failed attempts with tokens retained.

### 4.6 Pre-registration

The analysis plan, decision table and analysis code were written and hashed before the
confirmatory run. The repository was initialized *after* it, so the `prereg-v1` tag is
retroactive: **the freeze is real, but cryptographic proof of its ordering does not
exist.** This is stated rather than glossed. Analysis code hash at freeze:
`e584de6214e3db4e`; after a correction that aligned the code with the written plan
(§8): `27ee26977f34a714`.

---

## 5. Results

### 5.1 M1 — the small model: the interventions backfire

848 runs, zero harness errors.

| Suite · language | RTW | 95% BCa CI | Accuracy off → on | Claimable? |
|---|---|---|---|---|
| GSM8K · EN | **−109.7%** | (−336.6%, −3.2%) | 31.3% → 16.2% | **No** — gate failed |
| GSM8K · PT | −22.0% | (−163.2%, +33.9%) | 23.8% → 21.3% | Gate passed; CI spans zero |
| BFCL · EN | **−102.2%** | (−637.6%, +14.2%) | 15.4% → 3.8% | **No** — gate failed |
| BFCL · PT | +28.8% | (+5.0%, +47.9%) | 7.7% → 7.7% | Yes — but on 2 successes/arm |

Read plainly: in English the combined intervention **halves the success rate**, so the
token savings are consumed by paying for twice as many failures — cost per completed
task approximately doubles. In Portuguese accuracy largely survives but the token cost
still rises. One of four arms clears the gate with a positive RTW, and it rests on two
successful runs per condition, which is too thin to support weight.

**H1 and H2 are refuted for this model** in the English arms: the accuracy penalty far
exceeds the 3pp non-inferiority margin, so no efficiency claim is available at any RTW
value.

Interval widths are large. GSM8K · PT, the largest single arm at 640 runs, spans −163%
to +34% and is **genuinely inconclusive** rather than a demonstrated negative. §7
explains why.

### 5.2 M2 — the large model: the penalty disappears

106 runs on Llama-3.3-70B.

| Language | RTW | 95% BCa CI | Accuracy off → on | Gate |
|---|---|---|---|---|
| EN | +11.6% | (−19.9%, +30.9%) | 92.3% → 91.7% | **Passes** |
| PT | +15.3% | (−10.3%, +50.1%) | 92.9% → 100.0% | **Passes** |

Where the 3B model lost roughly half its successes under the same interventions, the
70B model loses **0.6 percentage points**, and in Portuguese accuracy rises. Both
gates pass; both point estimates are positive.

**Both intervals span zero.** The magnitude of the saving is therefore not
established, and "12–15% cheaper on a large model" is not a claim this study supports.
What is established is the qualitative difference in whether a saving is claimable at
all.

### 5.3 The matched-task control

M1's headline covers 40 GSM8K tasks; M2 covers seven. The difference between arms
could therefore be task difficulty rather than model scale.

Re-running M1's analysis restricted to **exactly the seven tasks M2 saw** settles this,
and the effect strengthens rather than weakens:

| Same seven tasks | Qwen2.5-3B | Llama-3.3-70B |
|---|---|---|
| EN accuracy, off → on | 50.0% → **14.3%** | 92.3% → **91.7%** |
| EN tokens per success | 3,043 → 15,123 (**5.0× worse**) | 2,200 → 1,946 |
| PT accuracy, off → on | 35.7% → **14.3%** | 92.9% → **100%** |
| PT tokens per success | 4,185 → 10,782 (**2.6× worse**) | 2,195 → 1,859 |

Identical tasks, identical schemas, identical protocol; opposite outcomes. On this
subset the small model's English RTW is **−396.9%** against the full-suite −109.7% —
the tasks M2 happened to receive are *harder* for the small model, not easier. Task
difficulty is ruled out as the explanation.

### 5.4 A Schema × Budget interaction (evidence bearing on H4)

Task `gsm_024`, isolated across five independent random seeds on M1, English:

| Condition | Successes |
|---|---|
| Raw schemas, either budget setting | **10 / 10** |
| Compressed schemas, unconstrained budget | 3 / 5 |
| Compressed schemas **and** capped budget | **0 / 5** |

Neither factor alone reliably breaks the task. Their combination reliably does. This
is a qualitative interaction, not merely sub-additivity — the joint condition behaves
unlike either component.

**A candidate explanation was tested and rejected.** The compressor had trimmed a
sentence from the calculator's description advising the model not to compute mentally.
Restoring that sentence (compiler v1.2) did **not** recover the accuracy — the cell
remained at 3/5. The convenient explanation was therefore falsified, the interaction
was left standing as a real effect, and the compiler was frozen rather than tuned
further. Continued patching at that point would have amounted to engineering away the
finding the experiment exists to detect.

Because this is a single task at n = 5 seeds, it is reported as **candidate evidence
for H4's refutation**, not as a confirmed factorial result.

### 5.5 Language effects are real, large, and not directional

Three tasks showed complete, seed-stable divergence between languages — and they do not
point the same way:

| Task | English | Portuguese | Mechanism |
|---|---|---|---|
| `gsm_029` | **0 / 5** | **5 / 5** | English introduces a multiplication with no basis in the problem |
| `gsm_039` | 4–5 / 5 | **0 / 5** | Portuguese drops one dimension of a two-dimensional quantity |
| `gsm_024` | S/B-dependent | 0 / 20 | Portuguese fails to extract a repeated-event multiplier |

Fisher's exact test on **seed-level** outcomes gives p = 0.008 for the first two.
(Cell-level counts were initially used and are inappropriate: the four S/B cells
sharing one seed were shown empirically to produce byte-identical model output, so
they are not independent trials. At one seed, no pattern can reach significance
regardless of how extreme it appears.)

All three translations were reviewed by a native speaker and approved unchanged. The
failures are in model comprehension, not translation quality.

The absence of a consistent direction argues **against a general "non-English tax"**
and in favour of task-specific comprehension failures that can land on either
language — including, in one case, on English. This is a weaker but better-supported
claim than the one the literature usually makes.

It also drove a method change: the localization protocol was revised mid-project from
back-translation review, which cannot detect this failure mode because the
translations are correct, to **running the model in both languages and comparing
outcomes directly**.

---

## 6. Interpretation

### 6.1 What is established

1. **On a 3B model, the combined intervention increases cost per completed task**, by
   roughly 2× on the full suite and 5× on the matched subset, and fails the accuracy
   gate in both English arms.
2. **On a 70B model, the accuracy penalty is absent** (92.3% → 91.7%), and both arms
   clear the gate.
3. **The difference is attributable to model scale, not task difficulty**, per the
   matched-task control.
4. **The effects are not additive** — at least one interaction exists in which two
   individually survivable interventions are jointly fatal.
5. **Language effects exist, are large, and are not unidirectional.**

### 6.2 What is not established

1. **That the interventions save money on large models.** Both M2 intervals span zero.
   A penalty disappearing is not a benefit appearing, and only the former is
   demonstrated here.
2. **That this generalizes across model families.** The scale claim rests on one model
   at each of two scales.
3. **Any precise RTW magnitude.** Interval widths are large throughout, for the reason
   given in §7.
4. **That multi-turn agentic workloads transfer.** That arm was not testable (§7).

### 6.3 Practical guidance

The actionable result is a decision rule, and it is asymmetric:

> **"Small cheap model + aggressive token compression" is the worst available
> combination.** It applies the accuracy cost of compression exactly where the model
> has least capacity to absorb it, and the resulting failures are billed at full
> price. On capable models the same compression appears safe — which is a weaker and
> more useful statement than "it pays off."

Second, and independent of scale: **measure tokens per success, not tokens per call.**
Every result in this study is invisible under per-call accounting; three of four M1
arms would have been reported as savings.

---

## 7. Threats to validity

**A later study measured exactly how underpowered — and it is worse than stated
here.** [Tolerance](https://github.com/hugocorreia123/tolerance-agent-evals) treats
cost-per-success as the ratio estimator it is, and reaches three conclusions about this
study. The naive interval on that metric achieves 39% coverage against a nominal 95%.
The minimum detectable effect for the GSM8K arm is 121–222%, so **the −109.7% headline
below sits beneath this study's own detection threshold**; the BCa interval excluded
zero only marginally, and BCa is asymmetric. And the closed-form MDE is itself
optimistic by 1.7–3.7×, making even those figures lower bounds. The conclusions in §5
should be read with that in mind: the direction is supported by the matched-task
control, the magnitude is not resolvable at this sample size.

**The study is underpowered for its own primary metric.** The power analysis estimated
the sample size needed to detect differences in *tokens* (n = 13–39). The primary
metric is tokens per *success*, which inherits accuracy variance through its
denominator. With this model's low and unstable accuracy, that denominator destroys
precision — hence intervals spanning −163% to +34%. n = 53 is adequate for what was
measured during planning; it is not adequate for what the design actually asks. **This
is the single most consequential methodological error in the study.**

**Pre-registration ordering is unproven.** See §4.6. The plan genuinely predates the
data; the timestamp proving it does not exist.

**M2 is quota-shaped, not design-shaped.** Seven tasks and two repeated calls per cell
is what a free-tier daily token ceiling permitted across three days, not a chosen
sample size.

**M2 deviates from the pre-registered model.** `gpt-oss-120b` was specified;
`llama-3.3-70b-versatile` was used, because the former proved incompatible with the
in-prompt tool protocol (§8). The substitution required no prompt change, so the arms
remain comparable — but it is a deviation, made on evidence and documented.

**Multi-turn transfer was not tested.** BFCL runs average ~94,000 tokens each. Against
a 100,000-token daily free-tier ceiling, the 208-run arm would require approximately
97 days. Single-turn transfer was measured; agentic multi-turn transfer was not.

**Suite size.** n = 53 rather than the planned 80, for the reasons in §4.3.

**One model family per scale.** "Small models break, large models absorb" is a
hypothesis supported by two models, not an established scaling law.

---

## 8. Methodological findings

Four defects were caught during the study that would each have corrupted a published
conclusion. They are reported because the manner of their detection is itself a
result.

**An inverted accuracy model.** `patsy`/`statsmodels` treats a boolean outcome column
as a two-level categorical and fits the wrong reference level. A synthetic dataset with
a planted true success rate of 0.80 returned a fitted **0.20** — an exact inversion.
Every accuracy-gate verdict would have been backwards. Detected only because the
analysis pipeline was validated against data with known answers before touching real
results.

**A misspecified primary metric.** The GLM path computed tokens per *attempt* rather
than per *success*. It agreed with the independent direct computation in every cell
where accuracy happened to match across conditions, and diverged by **over 100
percentage points** where it did not. Detected by the dual-computation cross-check,
which exists for precisely this class of error.

**A resume that re-ran everything it claimed to skip.** The harness supports resuming
interrupted runs. It was tested against an interruption and against a crash landing
mid-attempt, and passed both — but never against a **seedless provider**. Groq exposes
no sampling seed, so the runner records `seed_effective = None` while the resume built
its lookup key from the raw loop variable `0`. The keys never matched. One root cause
produced three symptoms, and **only the first was visible in console output**: cells
silently re-executing; duplicate attempt keys; and orphaned turn records from an
earlier aborted run inflating the token total of the attempt that followed them.
Symptoms two and three were caught only because the accounting layer cross-checks each
attempt's summary against the sum of its own turn records and refuses to proceed when
they disagree.

**In-prompt tool protocols are not portable across providers.** `gpt-oss-120b` ignores
an in-prompt JSON protocol and emits a **native function call**, which the provider
validates server-side and rejects with HTTP 400 — returning no usage data, so the
attempt cannot even be counted. Adding an explicit prohibition made it worse: the
request succeeded, consumed 370 output tokens, and returned **empty content**.
Llama-3.3-70B follows the identical protocol correctly with no prompt changes. This is
a portability constraint worth knowing for anyone building cross-provider agent
evaluations.

### The pattern

Sorted by *how* they failed, these fall into two groups needing different defences.

**Failures that announce themselves** — the HTTP 400, the rate-limit rejections — were
unmissable the moment the code ran against the real dependency. They cost time, not
correctness. The defence is to run the smallest real thing first.

**Failures that return a plausible number** are the dangerous class. An accuracy model
returning 0.20 for a true 0.80 does not crash; it produces a clean table with every
conclusion inverted. A metric computing the wrong denominator agrees with the right one
wherever accuracy happens to match. A resume that skips nothing still prints
"53 combos already have a real outcome, will be skipped."

Only one thing catches that class: **a second, independent computation of something
the code already believed.** Hand-typed ground truth was caught by re-derivation from
the dataset's own annotations; the misspecified metric by computing it a second way;
the inverted model by synthetic data with a known answer; the duplicate records by
checking each attempt's summary against the sum of its own turns.

The two silent defects that were *not* caught are exactly the two where no second
computation existed: the power analysis had no independent estimate to disagree with,
and nothing verified that the pre-registration commit was real.

"Independent" carries the weight. A second computation sharing the first's assumptions
confirms them rather than testing them — the dual-metric check worked because one path
ran through a GLM and the other was raw arithmetic over the records. A single
computation, however careful, has nothing to be wrong against.

---

## 9. Reproducibility

Every result file is append-only with a hash-pinned manifest recording the task suite,
configuration and code version that produced it. Token counts derive only from provider
usage fields or exact tokenizer counts; mock runs are flagged non-confirmatory and
excluded from analysis.

```bash
pip install -r requirements.txt

# mandatory pre-run gate: independently re-derive all ground truth
python -m prism.analysis.verify_suite prism/suite/w2_staging/gsm8k_extracted.json

# prove the multi-turn harness against the vendored simulator
python prism/scripts/smoke_test_bfcl.py

# M1 core arm — 848 runs, local, several hours
python run_pilot.py --model mlx \
  --tasks prism/suite/w2_staging/full_suite_n53.json --seeds 2

# M2 transfer arm — requires GROQ_API_KEY, stops cleanly at the daily quota
python run_pilot.py --model groq --model-id llama-3.3-70b-versatile \
  --tasks prism/suite/w2_staging/gsm8k_extracted.json --limit 12 --seeds 1

# analysis
python prism/scripts/run_confirmatory_analysis.py "$(ls -t results/*.jsonl | head -1)"

# compression / safety tradeoff of the frozen compiler
python prism/scripts/audit_compiler.py
```

Interrupted runs resume without repeating completed work via `--resume`. Attempts
interrupted mid-flight are backfilled as `harness_error` so their spent tokens remain
accounted for rather than disappearing.

`PRISM_SPEC.md` Appendix B records every design decision revised during the study, the
evidence that forced it, and the candidate fixes that were tested and deliberately not
applied.

---

## Appendix A — Full cell tables

### A.1 M2 — Llama-3.3-70B, 106 runs, 7 GSM8K tasks

| Cell | n | Successes | Accuracy | Total tokens | Tokens / success |
|---|---|---|---|---|---|
| S0B0L0 | 13 | 12 | 92.3% | 26,399 | 2,199.9 |
| S0B0L1 | 14 | 13 | 92.9% | 28,533 | 2,194.8 |
| S0B1L0 | 14 | 11 | 78.6% | 24,720 | 2,247.3 |
| S0B1L1 | 14 | 13 | 92.9% | 25,358 | 1,950.6 |
| S1B0L0 | 12 | 11 | 91.7% | 22,256 | 2,023.3 |
| S1B0L1 | 14 | 13 | 92.9% | 20,686 | 1,591.2 |
| S1B1L0 | 12 | 11 | 91.7% | 21,404 | 1,945.8 |
| S1B1L1 | 12 | 12 | 100.0% | 22,312 | 1,859.3 |

### A.2 M1 — Qwen2.5-3B restricted to the same 7 tasks, 112 runs

| Cell | n | Successes | Accuracy | Total tokens | Tokens / success |
|---|---|---|---|---|---|
| S0B0L0 | 14 | 7 | 50.0% | 21,304 | 3,043.4 |
| S0B0L1 | 14 | 5 | 35.7% | 20,927 | 4,185.4 |
| S0B1L0 | 14 | 4 | 28.6% | 20,138 | 5,034.5 |
| S0B1L1 | 14 | 5 | 35.7% | 21,235 | 4,247.0 |
| S1B0L0 | 14 | 5 | 35.7% | 21,022 | 4,204.4 |
| S1B0L1 | 14 | 1 | 7.1% | 14,439 | 14,439.0 |
| S1B1L0 | 14 | 2 | 14.3% | 30,245 | 15,122.5 |
| S1B1L1 | 14 | 2 | 14.3% | 21,563 | 10,781.5 |

The two tables share tasks, schemas, protocol and judging. The only difference is the
model.

---

## Appendix B — Data availability

| File | Contents |
|---|---|
| `results/r20260725_170738_270d87.jsonl` | M1 confirmatory run, 848 attempts |
| `results/r20260726_015506_1b37b6.repaired.jsonl` | M2 transfer arm, 106 attempts |
| `results/m1_matched_to_m2.jsonl` | M1 restricted to M2's seven tasks |
| `prism/suite/w2_staging/full_suite_n53.json` | The 53-task suite, EN + PT |

Raw and repaired M2 files are both retained. The raw file is the true append-only
record including the resume defect's footprint; the repaired file is a derived artefact
produced by `prism/scripts/repair_duplicate_attempts.py`, which renumbers repeated
attempts and separates orphaned records rather than discarding them.
