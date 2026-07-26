# PRISM — The True Cost of a Token
### Build Specification v2 · July 2026

One factorial experiment measuring the **joint, decomposed token waste** of an agentic LLM workload — across schema bloat, reasoning verbosity, and language — on entirely free compute. Design produced by two explicit design→critique→redesign cycles; the decisions below each name the critique they answer.

---

## 1 · Hypotheses (falsifiable, pre-registered)

- **H1 (Structure).** Structure-aware schema compression reduces all-in tokens per success by ≥25% with accuracy non-inferior at δ = 3pp, and outperforms generic compression (LLMLingua-2) on tool-call accuracy at equal token budgets.
- **H2 (Overthinking).** Training-free reasoning budgets reduce all-in tokens per success by ≥20% with accuracy non-inferior at δ = 3pp on the factorial suite; the effect shrinks or reverses on the hardest quartile of items (predicted failure boundary — a negative result here is a finding).
- **H3 (Language).** Portuguese carries a ≥12% all-in token premium over English at matched task success on the same model, decomposable into a tokenizer-fertility component and a model-competence component, attributed separately.
- **H4 (Interaction / the novel claim).** The joint saving of all optimizations differs from the sum of individual savings by a measurable interaction term; we report its size and sign. Prediction: sub-additive (compressed schemas reduce what budgeted reasoning can cut). Nobody has published this number.

Failure conditions are explicit: if any Hx's CI excludes its margin in the wrong direction, that hypothesis is reported as refuted. Negative results are published with equal prominence.

## 2 · Experimental design

**Factorial core: 2 × 2 × 2, within-task, paired.**

| Factor | Level 0 (off) | Level 1 (on) |
|---|---|---|
| **S** — Schema | Raw JSON tool schemas | Frozen structure-aware compressed schemas (v-tagged, §6) |
| **B** — Budget | Unconstrained reasoning | Concision system prompt + hard output cap (per-task cap = 1.5× median correct-solution length from pilot) |
| **L** — Language | English user content | Portuguese user content (schemas & system prompts stay English in both — the ecological reality of agents today; stated, not smuggled) |

Every task runs in all 8 cells (paired design → within-item contrasts, maximal power per run).

**Models.**
- **M1 (factorial core):** Qwen2.5-3B-Instruct, local via MLX on Apple Silicon — uncapped, exact token accounting, the bulk of runs.
- **M2 (validation arm):** openai/gpt-oss-120b via Groq free tier — smaller n, checks that effects transfer to a frontier-adjacent model. TPM-cap-aware batching.
- **M3 (ablations only):** Llama-3.1-8B (local) — depth on Tier-2 slices, not in the core.

**Run budget (fits free compute — answers critique 3; n revised from 80→53 during W2, see Appendix B).**

| Arm | Cells | Tasks | Seeds | Runs | Est. tokens | Where |
|---|---|---|---|---|---|---|
| Core (M1) | 8 | 53 | 2 | 848 | ~2.8–3.3M | Local MLX, uncapped |
| Validation (M2) | 8 | 27 | 1 | 216 | ~0.8M | Groq free, TPM-aware batching |
| Ablations (Tier 2) | — | see §3 | — | ~2,500 | ~3M | Local |

## 3 · Task suite

**Tier 1 — the factorial suite (n = 53, revised down from the planned 80 — see Appendix B for the reasoning).** Composed from validated sources, not invented (answers critique 4):
- 13 multi-turn tool-use tasks drawn from BFCL-v4's multi-turn base set (the live repo now ships v4, not v3 — corrected from the original spec), restricted to single-simulator-class (GorillaFileSystem-only) tasks; every ground-truth trajectory replays cleanly against BFCL's own vendored simulator before acceptance. The other 187 base-set tasks mix multiple simulator classes, deliberately deferred rather than rushed.
- 40 tool-augmented reasoning tasks: GSM8K-hard items (≥3 reasoning steps) wrapped with a calculator tool + a lookup tool, `solution_expr` auto-derived and machine-verified from GSM8K's own `<<expr=result>>` annotations — never hand-typed. 69 candidates yielded 40 acceptances; 29 dropped as unverifiable rather than guessed.

**Localization protocol (PT) — as actually run, superseding the original back-translation plan.** MT draft → native post-edit (Hugo) → **run the candidate model on both languages and flag any large accuracy gap** (`comprehension_check.py`), not back-translation review. This substitution is load-bearing, not cosmetic: the pilot's `calcA_002` finding showed a *faithful* translation can still flip a small model's comprehension entirely, and two W2 pilot findings (`gsm_029`, `gsm_039` — confirmed at 5/5 independent seeds each) replicated exactly that pattern on structurally faithful translations. Back-translation would not have caught either. Only user-facing content is localized (§2); promotion from draft to real, runnable content is one-directional and audited (which drafts were approved verbatim vs. edited — `scripts/promote_pt.py`).

**Tier 2 — ablation slices (power where the factorial is thin).**
- Language: FLORES-200 fertility across o200k / cl100k / Llama-3 / Gemma / Qwen tokenizers (CPU-only); Belebele EN-vs-PT parallel comprehension on M1/M3.
- Overthinking: full GSM8K test (1,319 items) + MATH-500 on M1 — large-n Pareto frontier.
- Structure: BFCL slice (200 calls) under raw vs LLMLingua-2 vs TOON vs the frozen compiler.

## 4 · Metrics — measurement layer (real) vs pricing layer (transform)

**Primary metric: all-in tokens per success (answers critique 2).**

For model m, language ℓ, condition c:

```
T(m, ℓ, c) = Σ over ALL attempts (tok_in + tok_out, including failed and retried attempts)
             ─────────────────────────────────────────────────────────────────────────
                                  number of successful items
```

Failures cost tokens; they stay in the numerator. Token counts come exclusively from API `usage` fields (M2) or the tokenizer's own count on exact I/O (M1). Retries are logged as separate attempts with a `retry` flag; harness errors (non-model failures) are excluded from T but reported as a rate.

**RTW — Recoverable Token Waste (the headline, gate included by definition):**

```
RTW(m, ℓ) = 1 − T(m, ℓ, all-on) / T(m, ℓ, all-off)

CLAIMABLE only if: acc(all-on) ≥ acc(all-off) − δ,  δ = 3pp,
                   by paired bootstrap 95% CI on the accuracy difference.
Otherwise: no single RTW is reported — the Pareto frontier is.
```

**Attribution.** RTW is computed two ways and reported side by side: (a) the marginal contrast from the GLMM in §5 — the primary estimate; (b) the direct paired all-on/all-off ratio above — a transparent, model-free cross-check. Agreement between them is itself evidence the finding survives its own modeling choices. Main effects are reported as shares of RTW; the interaction term (measured joint RTW vs the additive sum of main effects) **is** the H4 result, tested for equivalence-to-zero (not just "CI includes zero") per §5.

**Workload-weighted extrapolation (answers critiques 3-of-design and 6-of-spec).** Empirical component mixes (schema-input / reasoning-output / user-content shares of the token bill) measured from three observed sources: (1) SWE-bench agent trajectories (public), (2) a second public agent-trace set, (3) instrumented traces from Hugo's own live agents (Voyager, Tracer, Turbine — they already log). RTW reported at each of the three observed mixes and as a surface over the mix simplex. Never labeled "representative"; labeled "at three observed mixes."

**Pricing layer (answers critique 1-of-design).** Euros are a transparent transform, never a measurement: three dated price-sheet snapshots (one large-lab API, one mid-tier, one open-weight hosting), applied to measured tokens, with a sensitivity plot. Every € figure carries the sheet and date.

## 5 · Statistical analysis plan (pre-registration summary; full text in Appendix A)

*Rewritten to the maximum defensible rigor (design → critique → redesign, same as everything else in this spec). "Best" means maximally rigorous **and** maximally honest — three tempting additions were considered and rejected; see the end of this section for why.*

**Estimation — proper models, not raw cell means.**
- **Token cost (T).** Negative-binomial GLMM: fixed effects S × B × L, full factorial including all interactions (required by H4 — never selected away), random intercept for `task_id`. Truncated-at-cap attempts are real, fully-observed costs for this question (the tokens were genuinely spent) — not treated as censored.
- **Accuracy.** Mixed-effects logistic regression, same fixed-effect structure + task random intercept — respects the binomial, clustered structure that raw cell proportions ignore.
- **RTW.** Reported two ways (§4): the GLMM's marginal contrast (primary) and the direct paired ratio (cross-check).

**Uncertainty — precisely specified, not "paired bootstrap."**
Cluster (case) bootstrap: resample `task_id`s with replacement, each resampled task carrying its full 8-cell record intact. This is the statistically correct way to bootstrap a paired, repeated-measures ratio; row-level resampling would break the pairing and understate every CI. 10,000 resamples minimum (free; 20,000 if runtime allows). **BCa** intervals, since RTW is a skewed ratio, not a symmetric statistic — plain percentile CIs reported alongside as a check that the correction isn't doing anything surprising.

**Testing.** Non-inferiority at δ = 3pp remains the PRIMARY, frequentist, fixed gate for H1–H3 — unchanged, because this is what makes the claim falsifiable. **For H4 specifically**, add a formal **TOST equivalence test** against a pre-specified negligibility bound (interaction < 2pp of baseline RTW): a CI that merely includes zero is not proof of additivity, and "the taxes are additive" deserves the same positive-support standard as every other claim here.

**Multiplicity — two tiers.** Holm–Bonferroni across the four pre-registered primary hypotheses (H1–H4), as before — correct for a small, fixed primary family. **Benjamini–Hochberg (FDR)** separately across the secondary/exploratory family (per-mix RTW points, per-model transfer checks, per-cell contrasts) — reported in a clearly separate table, labeled exploratory, never mixed into the primary claim.

**Sensitivity battery — small, fixed, reported together, never fished.** Three pre-specified checks accompany the primary result in one table: (1) δ swept at 1.5pp / 3pp / 5pp; (2) with vs. without truncated-at-cap attempts; (3) mean- vs. median-based token statistic. A result that survives only one cell of this table is reported as fragile, not hidden.

**Design-quality controls (free, pure upside).** Execution order of each task's 8 cells is randomized per task, not fixed S→B→L nesting — guards against any time-varying confound (server load, thermal throttling) over a multi-hour local run. Every record already carries a wall-clock timestamp (§6); run-order becomes a pre-specified covariate for a stated robustness check, no new field required.

**Power — formula plus simulation.** The pilot's closed-form estimate (§7) is the planning number that supported settling on n = 53 (Appendix B). Before W4, a simulation-based check runs the actual planned pipeline — GLMM, cluster bootstrap, non-inferiority gate — on synthetic datasets drawn from the pilot's variance components, reporting empirical power and false-positive rate for the real procedure at n = 53 rather than a formula that assumes a simpler test than the one actually run. Free; not yet run.

**A pre-specified decision table** (Appendix A) maps every possible outcome pattern for H1–H4 to its formal conclusion — supported / refuted / inconclusive — fixed before confirmatory runs, removing post-hoc interpretive room.

**Exclusion rules**, unchanged: harness errors excluded (reported separately); refusals count as failures; truncation-at-cap counts as a failed attempt for accuracy, tokens retained in T.

**Deliberately not added, and why.** A fully Bayesian *primary* analysis was considered and rejected — it would quietly abandon the hard claim/no-claim gate that gives this spec its falsifiability, and switching frameworks after seeing data invites fair suspicion of framework-shopping. Instead, a pre-specified **Bayesian hierarchical model runs as a formal secondary layer**, reporting full posteriors (e.g. "P(RTW > 20%)") — genuine added nuance, zero risk to the primary gate. **Group-sequential/adaptive stopping** was considered and rejected for this run: real implementation risk (alpha-spending code that itself needs freezing, no dry run before it matters) for a design whose actual bottleneck is Groq's rate limit on the validation arm, not compute cost on the free local core — bad complexity-to-benefit ratio here; the right call for a larger *future* confirmatory study, not this one. **Post-hoc model selection** (AIC/BIC trimming of interaction terms) was rejected outright — it would be p-hacking the exact term H4 exists to test. The factorial structure is fixed by pre-registration; model diagnostics (residuals, per-task influence) check validity, never select structure.

Analysis code frozen and hash-pinned before confirmatory runs; pilot data never enters confirmatory analysis.

## 6 · Frozen components & reproducibility

- **Schema compiler v1.2** frozen at end of W2 (answers critique 7). Two disclosed, pre-confirmatory revisions from the original v1.0: v1.1 added deontic constraint-clause preservation after a real BFCL task showed the blunt char-cap silently dropping safety-relevant text (`mv`'s "cannot be a path"); v1.2 added a second, distinct marker category for purposive clauses after a real MLX run traced a measured, 5-seed-replicated accuracy gap to a dropped usage-guidance sentence in `calculator`'s description. A third candidate fix was tested and explicitly **not** applied: restoring that one sentence did not recover the accuracy gap (still 3/5 vs 0/5 seeds), revealing the residual gap as a genuine S×B interaction rather than a droppable clause — treated as a pilot finding (candidate evidence for H4) rather than a compiler defect, and the compiler was frozen at v1.2 rather than patched further. Full audit trail: `scripts/audit_compiler.py`, PRISM_SPEC.md Appendix B, W2_STATUS.md.
- Any change to the frozen compiler forces a re-run of affected cells.
- Tokenizer versions pinned (`tiktoken`, HF `tokenizers` versions recorded); price sheets snapshotted with dates; seeds fixed; environment in `uv.lock`; every run emits a JSON record (task id, cell, attempt, tokens in/out, success, latency, retry flag).
- Repo layout: `/suite` (tasks EN+PT), `/harness` (runner + accounting), `/compilers` (frozen schema compiler + baselines), `/analysis` (pre-registered notebooks), `/traces` (mix measurement), `/results` (append-only JSONL), `/report`.

## 7 · Timeline with numeric gates (answers critique 8)

| Week | Work | Gate to proceed |
|---|---|---|
| **W1** ✅ | Harness + pilot through all 8 cells on M1; variance & power check | **Satisfied**: 0 harness errors across 3 real MLX pilot runs; worst-cell accuracy 33.3% (>15%); paired-log-token power → n=13–39 needed, comfortably under any planned n |
| **W2** ✅ | Build Tier-1 suite (compose + localize); freeze compiler | **Satisfied, verified not self-reported**: suite built (53 tasks, both sources machine-verified), compiler frozen at v1.2, 53/53 PT items promoted after native review (0% required correction — see Appendix B), confirmed by re-running the suite and observing zero `SKIPPED` cells where every prior run showed exactly 4/8 per task |
| **W3** ← next | Lock pre-registration (git commit + tag, not OSF — see note above Appendix A); dry-run 20 tasks end-to-end | Pre-reg locked before any confirmatory run — hard gate, same as before, different mechanism. Dry-run: **done** (320 runs, zero harness_error, zero unexpected skips). |
| **W4–5** | Factorial core on M1 (848 runs); M2 validation arm (216 runs) | ≥95% of planned runs completed with clean accounting |
| **W6** | Tier-2 ablations (GSM8K full, Belebele, BFCL, FLORES fertility) | — |
| **W7** | Trace instrumentation, three mixes, RTW surface; sensitivity pricing | — |
| **W8** | Report + repo release; leaderboard **optional afterward** (answers critique 10) | — |

Every stage is standalone-publishable; stopping early still ships a finding.

## 8 · Deliverables

1. **Pre-registration, locked via git commit + tag** (Appendix A text) — timestamped before confirmatory runs. Not filed on OSF: the audience for this project is a GitHub portfolio, not peer review, so the formal registry's specific value (defending a claim against academic scrutiny) doesn't apply — but the underlying discipline it protects (lock the plan before seeing confirmatory data, so a replicated pilot finding isn't secretly just re-discovering what was already known) is kept anyway, via the mechanism the audience already reads natively: a dated, hash-identified git tag.
2. **Open repo** with the suite (EN+PT), harness, frozen compiler, accounting protocol, and append-only results.
3. **Report** (paper-style + blog): the RTW headline with factorial decomposition, the H4 interaction number, honest confound section (PT competence vs tokenizer premium, decomposed per H3), Pareto frontiers, and the priced sensitivity analysis.
4. *(Optional, post-report)* Streamlit leaderboard in the portfolio's visual language.

## 9 · Risks and their honest outcomes

- **Budgets hurt accuracy on hard items** → H2's predicted failure boundary; publish the boundary.
- **Compression breaks tool-call validity** → per-failure-mode taxonomy is the contribution; publish where it breaks.
- **PT premium is smaller on o200k than expected** → the generational-trend finding ("the tax is shrinking") is itself the story.
- **Interaction term ≈ 0** → H4 refuted: "the taxes are additive" is a clean, useful, citable negative result.
- **Groq flakiness corrupts M2** → M2 is a validation arm, not the core; the core is local and uncapped by design.
- **Scope creep** → the gates are numeric and the leaderboard is out of scope until the report ships.

---

## Appendix A — Pre-registration (locked via git commit + tag, not OSF)

**Why git, not OSF.** This project ships as a GitHub portfolio piece, not an academic submission — the audience is technical readers evaluating engineering and research rigor, not peer reviewers scrutinizing a claim for citation. OSF's specific function (making a confirmatory result immune to "did you just find what you already knew was there") isn't needed for that audience in the same way, but the property itself is worth keeping: the text below is committed and tagged in the repo (`prereg-v1`) *before* any confirmatory-scale run touches real compute. The tag's timestamp is the pre-registration date; the commit diff against later results is the honesty check. Same discipline, a mechanism the actual readers already know how to verify.

**Title.** Prism: a factorial decomposition of recoverable token waste in agentic LLM workloads.
**Hypotheses.** H1–H4 as §1, with margins and directions as stated.
**Design.** 2×2×2 within-task factorial (Schema × Budget × Language), paired; n = 53 tasks × 2 seeds on M1 (Qwen2.5-3B-Instruct, local), n = 27 × 1 on M2 (gpt-oss-120b, Groq) as a transfer check. Task provenance: BFCL-v4 multi-turn base set, single-simulator-class only (13) + tool-wrapped GSM8K-hard with machine-verified `solution_expr` (40); PT localization by MT + native post-edit + model-run comparison check (`comprehension_check.py`, supersedes the originally-planned back-translation spot-check — see §3). Schemas and system prompts remain English in all cells.
**Primary outcome.** All-in tokens per success (all attempts' input+output tokens ÷ successes), per cell. **Secondary.** Accuracy; per-component token shares; latency.
**Analysis.** Negative-binomial GLMM (tokens) and mixed-effects logistic GLMM (accuracy), fixed effects S×B×L full factorial + task random intercept; RTW from the GLMM's marginal contrast, cross-checked against the direct paired ratio. Cluster (task-level) bootstrap, 10k+ resamples, BCa intervals. Non-inferiority at δ = 3pp gates H1–H3; TOST equivalence test (bound 2pp of baseline RTW) governs H4's additivity claim. Multiplicity: Holm–Bonferroni on H1–H4 (primary), Benjamini–Hochberg on the exploratory family (separate table). Pre-specified sensitivity battery: δ ∈ {1.5, 3, 5}pp; with/without truncated attempts; mean vs. median token statistic. Cell execution order randomized per task. Secondary Bayesian hierarchical model reports full posteriors; never substitutes for the primary gate. Exclusions: harness errors (reported, excluded); refusals = failures; cap-truncations = failed attempts, tokens retained. A fixed decision table maps every H1–H4 outcome pattern to supported/refuted/inconclusive before any confirmatory run.
**Stopping rule.** Fixed n; no optional stopping. Pilot data (W1–W2, including the comprehension-check forensics) is exploratory and excluded from confirmatory analysis.
**Materials & code.** Frozen at pre-registration: task list hash, compiler v1.2 hash, analysis code hash = `e584de6214e3db4e` (`prism/analysis/{bootstrap,glm,confirmatory}.py`, built and verified — not merely planned — before this pre-registration; see Appendix B for the verification trail, including a real bug caught before it could touch data).

## Appendix B — What died between v1 and v2 (the audit trail)

Invented workload weights → three observed mixes. Additive RTW → measured joint contrast + interaction term (H4). Imputed euros as headline → tokens measured, euros as a dated transform with sensitivity. Tokens-per-correct → all-in cost per success with failures priced in and the non-inferiority gate inside the definition. Three models in the core → two, with a budget table that actually fits free compute. Hand-built tasks → composed from validated sources with a localization protocol. "We will pre-register" → the pre-registration text above. Leaderboard as deliverable → optional, after the science.

**Statistics v2.1 (this round — "best possible" pushed and then cut back to defensible).** Raw cell means → GLMM (negative-binomial for tokens, logistic for accuracy) with task random intercepts. Vague "paired bootstrap" → precisely specified cluster bootstrap (resample task IDs, not rows) with BCa intervals. "CI includes zero" standing in for "additive" → a formal TOST equivalence test for H4, so that claim has to be earned like every other. Single-tier Holm → two-tier: Holm on the primary four, Benjamini–Hochberg on everything exploratory, kept in a separate table. Closed-form power only → formula plus a simulation of the actual analysis pipeline. Fixed cell order → randomized per task, a free confound guard. *Considered and rejected*: Bayesian analysis as the primary framework (demoted to a secondary posterior-reporting layer, so the falsifiable gate stays intact); group-sequential/adaptive stopping (deferred to a hypothetical larger future study — bad complexity-to-benefit ratio here); post-hoc model selection on the interaction term (would p-hack the exact thing H4 exists to test).

**Localization outcome (closing W2).** 53/53 PT drafts promoted after native review: **0% required correction** — every draft approved verbatim. Consistent with, not contradicted by, the `gsm_029`/`gsm_039` findings: both had faithful translations and still produced large, real, seed-replicated accuracy effects, so a near-zero edit rate is what the evidence predicted, not a skipped step. Full audit trail (which drafts were touched, snapshot vs. final) preserved via `*_pt_draft_v1_original.json` and `scripts/promote_pt.py`'s diff report.

**Confirmatory pipeline built and verified (closing the gap between "planned" and "exists").** §5's GLM/bootstrap/TOST/decision-table design was a specification until this pass; it's now `prism/analysis/{bootstrap,glm,confirmatory}.py`, hash `e584de6214e3db4e`. Every piece tested against synthetic data with a KNOWN true answer, not just "runs without crashing": the cluster bootstrap's BCa interval hit 95.0% coverage over 200 independent simulated datasets against a 95% nominal target; the GLM layer recovered a planted sub-additive S×B interaction (mimicking the real `gsm_024` pattern) within expected small-sample error; the accuracy gate was proven to both pass a genuinely non-inferior scenario and correctly block a planted accuracy collapse; TOST was proven to correctly call a large planted interaction non-equivalent and a negligible one equivalent, in both directions. **A real, dangerous bug was caught in this process, not after**: `patsy`/`statsmodels` silently treats a boolean outcome column as a 2-level category and fits the wrong reference level — a planted true P(success)=0.80 came back as a fitted 0.20, an exact inversion, which would have flipped every accuracy-gate conclusion in the real analysis had the recovery test not existed. Fixed by explicit int(0/1) coercion at the source, documented in the code itself so it can't silently regress. A second, narrower gap found the same way: the negative-binomial dispersion parameter was silently fixed at 1.0 by statsmodels' GLM default rather than estimated — switched to full-MLE fitting. A third: the GLM produced a confident-looking RTW number from BFCL's mock data despite zero successes across all 208 attempts (`PerfectSeparationWarning`, easy to miss on stderr) — now explicitly detected and surfaced in the CLI's own output, refusing to report a number from a non-identified model rather than trusting it silently. The cell-execution-order randomization §5 committed to was also still unbuilt at this point — added to `run_pilot.py`, deterministically seeded per task for reproducibility, verified to change only ordering (same outcome set) and to differ between tasks (not one global shuffle).

**Resume support, built and verified before it was needed for real (not after a real crash forced it).** 848+216 real runs is realistically many hours; no mechanism existed to recover from an interruption without either losing all progress or manually reconstructing what was left. Built `RunWriter.resume()` (reopens the same run_id/file, refuses loudly on config or suite hash mismatch — resuming under a different model/budget/suite would silently mix incompatible conditions under one run_id) and `--resume PATH` on `run_pilot.py`. Verified against an artificially crashed-and-resumed run: the naive version passed an easy case but failed a harder one caught by the same test — a crash landing *mid-attempt* (turn records written, summary never reached) left orphaned tokens that, on naive resume, collided with the fresh re-run under the same attempt number, corrupting the invariant check. Fixed properly: orphaned partial attempts are backfilled as `harness_error` (same bucket as any other interrupted generation — reported, excluded from analysis, never invisible), and the re-run gets a fresh attempt number. Final check: an interrupted-and-resumed run's real outcomes are byte-identical to an uninterrupted reference run of the same suite — 160/160 matching, zero duplicates, zero gaps.

**W1/W2 pilot audit (this round — the real cost of contact with real models).** n = 80 → **53** (13 BFCL + 40 GSM8K): not a shortfall, a disclosed scope decision — the three BFCL variant files each confound a different capability with the S/B factors, excluded rather than mixed in uninspected, and padding with more GSM8K would have erased the multi-turn diversity the 40/40 split existed for. Back-translation → **model-run comparison** (`comprehension_check.py`): `calcA_002` (W1) and two W2 findings (`gsm_029`, `gsm_039`, both confirmed at 5/5 independent seeds) all involved *faithful* translations that still flipped comprehension — a check that never runs the model can't catch that. Naive percentage-gap flagging → **Fisher's exact test on seed-level outcomes**, not cell-level: the 4 (S,B) cells sharing one seed were shown empirically non-independent (byte-identical model output across all four), so treating them as 4 trials overstated power; at n=1 seed the correctly-computed p-value is 1.000 regardless of how extreme the pattern looks — provably, not just cautioned. Compiler v1.0 → v1.1 → v1.2, two real, evidenced, disclosed revisions (§6) — and a third candidate fix explicitly **not** made: restoring `gsm_024`'s dropped sentence didn't recover its accuracy gap, which is now documented as a live S×B interaction (candidate H4 evidence) rather than chased into a compiler that keeps changing until the finding disappears. That refusal to over-fit the instrument is itself a decision worth recording: the same discipline that says "fix real gaps" also says "stop when the gap stops being about the instrument."
