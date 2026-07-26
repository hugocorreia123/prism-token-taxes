"""The confirmatory analysis pipeline — wires the tested bootstrap.py
and glm.py primitives into the actual pre-registered quantities:
RTW (dual-computed), the H1-H3 non-inferiority gate, H4's TOST
equivalence test, Holm/BH multiplicity correction, and the fixed
decision table. See PRISM_SPEC.md §5 for the design and its critique
trail.

Every reported CI comes from the cluster bootstrap (bootstrap.py),
never from a model's own standard errors — GLM point estimates only.
"""
from __future__ import annotations

import statsmodels.stats.multitest as smm

from .bootstrap import cluster_bootstrap, jackknife, bca_interval, percentile_interval
from .glm import fit_token_glm, fit_accuracy_glm, marginal_prediction

DELTA_PP = 0.03      # non-inferiority margin, H1-H3
TOST_BOUND_FRAC = 0.02  # H4 equivalence bound, as a fraction of baseline RTW


def _direct_ratio(records: list, on_cell: str, off_cell: str) -> tuple:
    """The direct paired all-in-tokens-per-success ratio (§4) — the
    transparent, model-free cross-check against the GLM's marginal RTW."""
    on = [r for r in records if r["cell"] == on_cell]
    off = [r for r in records if r["cell"] == off_cell]
    tok_on = sum(r["tok_in_total"] + r["tok_out_total"] for r in on)
    tok_off = sum(r["tok_in_total"] + r["tok_out_total"] for r in off)
    succ_on = sum(1 for r in on if r["success"])
    succ_off = sum(1 for r in off if r["success"])
    return tok_on, succ_on, tok_off, succ_off


def _check_separation(df, min_successes: int = 3) -> str | None:
    """A GLM fit on a near-constant outcome (all-success or all-fail)
    is not reliably identified — statsmodels warns about this on
    stderr, easy to miss. Surface it in the CLI's own output instead,
    and refuse to trust the resulting number. Found via mock data with
    zero BFCL successes producing a silent, meaningless RTW."""
    n_succ = df["success"].sum()
    n = len(df)
    if n_succ < min_successes or (n - n_succ) < min_successes:
        return (f"only {n_succ}/{n} successes — accuracy model is not "
               f"reliably identified (perfect/near-perfect separation). "
               f"Any RTW number here is not trustworthy.")
    return None


def compute_rtw(records: list, task_id_field: str = "task_id",
                n_boot: int = 2000, seed: int = 0) -> dict:
    """RTW = 1 - T_on/T_off, all-on (S1B1) vs all-off (S0B0), per
    language. Reports BOTH the GLM-marginal estimate (primary) and the
    direct paired ratio (cross-check) — agreement between them is
    itself evidence the finding isn't a modeling artifact (§4)."""
    import pandas as pd
    df = pd.DataFrame(records)
    separation_warning = _check_separation(df)
    tok_model = fit_token_glm(df)
    acc_model = fit_accuracy_glm(df)

    task_ids = sorted(set(r[task_id_field] for r in records))
    by_task = {}
    for r in records:
        by_task.setdefault(r[task_id_field], []).append(r)

    results = {}
    for L in (0, 1):
        T_on_glm = marginal_prediction(tok_model, 1, 1, L)
        T_off_glm = marginal_prediction(tok_model, 0, 0, L)
        rtw_glm = 1 - T_on_glm / T_off_glm

        acc_on_glm = marginal_prediction(acc_model, 1, 1, L)
        acc_off_glm = marginal_prediction(acc_model, 0, 0, L)

        on_cell, off_cell = f"S1B1L{L}", f"S0B0L{L}"
        tok_on, succ_on, tok_off, succ_off = _direct_ratio(
            records, on_cell, off_cell)
        T_on_direct = tok_on / succ_on if succ_on else float("inf")
        T_off_direct = tok_off / succ_off if succ_off else float("inf")
        rtw_direct = (1 - T_on_direct / T_off_direct
                     if succ_on and succ_off else None)

        def rtw_stat(resampled_ids, L=L):
            subset = [r for tid in resampled_ids for r in by_task.get(tid, [])]
            t_on, s_on, t_off, s_off = _direct_ratio(
                subset, f"S1B1L{L}", f"S0B0L{L}")
            if not (s_on and s_off):
                return None
            return 1 - (t_on / s_on) / (t_off / s_off)

        boot = [x for x in cluster_bootstrap(task_ids, rtw_stat, n_boot, seed) if x is not None]
        theta_hat = rtw_direct if rtw_direct is not None else (
            sum(boot) / len(boot) if boot else None)
        gate_pass = None
        bca = pct = (None, None)
        if boot and theta_hat is not None:
            jack = [x for x in jackknife(task_ids, rtw_stat) if x is not None]
            if len(jack) >= 3:
                bca = bca_interval(theta_hat, boot, jack)
            pct = percentile_interval(boot)
            acc_gap = acc_on_glm - acc_off_glm
            gate_pass = acc_gap >= -DELTA_PP

        results[f"L{L}"] = {
            "rtw_glm_marginal": rtw_glm,
            "rtw_direct_paired": rtw_direct,
            "rtw_bca_ci": bca,
            "rtw_percentile_ci": pct,
            "acc_on_glm": acc_on_glm, "acc_off_glm": acc_off_glm,
            "gate_delta_pp": DELTA_PP,
            "claimable": bool(gate_pass) if gate_pass is not None else False,
            "separation_warning": separation_warning,
        }
    return results


def tost_equivalence(diff_boot: list, bound: float, alpha: float = 0.05) -> dict:
    """Two one-sided tests for H4: is the true difference within
    [-bound, +bound]? Using the bootstrap distribution directly —
    reject 'not equivalent' (declare equivalence) only if the fraction
    of draws beyond EACH bound is below alpha on that side."""
    n = len(diff_boot)
    p_below = sum(1 for d in diff_boot if d <= -bound) / n
    p_above = sum(1 for d in diff_boot if d >= bound) / n
    equivalent = (p_below < alpha) and (p_above < alpha)
    return {"p_lower": p_below, "p_upper": p_above,
           "bound": bound, "equivalent": equivalent}


def multiplicity_correct(pvals: dict, method: str) -> dict:
    """method='holm' for the primary H1-H4 family, 'fdr_bh' for the
    exploratory family — statsmodels' implementation, not reimplemented."""
    names = list(pvals.keys())
    raw = [pvals[n] for n in names]
    reject, corrected, _, _ = smm.multipletests(raw, method=method, alpha=0.05)
    return {n: {"p_raw": raw[i], "p_corrected": corrected[i],
                "reject": bool(reject[i])}
            for i, n in enumerate(names)}


def decision_table(h1, h2, h3, h4) -> dict:
    """Fixed, pre-specified mapping from test outcomes to a label —
    removes post-hoc interpretive room (§5). Each h1-h3 arg: dict with
    'claimable' (bool) and 'rtw' (float). h4: dict from tost_equivalence.

    H4 logic: 'supported (additive)' when TOST declares equivalence.
    'refuted (real interaction)' requires CONFIDENT evidence the truth
    lies beyond one bound — most of the bootstrap mass past -bound
    (p_lower high) or past +bound (p_upper high), i.e. p_lower or
    p_upper >= (1 - alpha), matching the same 0.95 confidence level
    used everywhere else. Anything short of both thresholds is
    'inconclusive' — genuinely ambiguous or underpowered, not a claim
    either way. (An earlier version of this check compared both
    p-values against alpha in the same direction, which is incoherent
    since they test opposite tails — caught by this test suite before
    ever running on real data.)"""
    def label_gated(h, min_rtw=0.0):
        if not h["claimable"]:
            return "inconclusive (accuracy gate failed — report frontier only)"
        return "supported" if h.get("rtw", 0) > min_rtw else "refuted"

    CONFIDENT = 0.95
    if h4["equivalent"]:
        h4_label = "supported (additive)"
    elif h4["p_lower"] >= CONFIDENT or h4["p_upper"] >= CONFIDENT:
        h4_label = "refuted (real interaction)"
    else:
        h4_label = "inconclusive"
    return {"H1": label_gated(h1), "H2": label_gated(h2),
           "H3": label_gated(h3), "H4": h4_label}
