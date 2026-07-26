"""Cluster bootstrap + BCa — the foundation of the confirmatory analysis.

Generic by design: takes a list of cluster (task) ids and a function
that computes whatever statistic from a SUBSET of those ids. Resamples
task ids WITH replacement (never individual rows) — a row-level
bootstrap would break the pairing the spec's whole design depends on.
"""
from __future__ import annotations

import math
import random
from collections import Counter

from scipy.stats import norm


def cluster_bootstrap(task_ids: list, statistic_fn, n_resamples: int = 10000,
                      seed: int = 0) -> list:
    """Resample task_ids with replacement n_resamples times; for each
    resample, call statistic_fn(resampled_ids) — the caller looks up
    each id's full record set (all cells, all seeds) and computes
    whatever statistic from exactly that resampled population,
    including a task appearing multiple times if drawn more than once.
    Returns the list of bootstrap statistic values."""
    rng = random.Random(seed)
    ids = list(task_ids)
    n = len(ids)
    out = []
    for _ in range(n_resamples):
        resampled = rng.choices(ids, k=n)
        out.append(statistic_fn(resampled))
    return out


def jackknife(task_ids: list, statistic_fn) -> list:
    """Leave-one-task-out — needed for the BCa acceleration constant."""
    ids = list(task_ids)
    out = []
    for i in range(len(ids)):
        out.append(statistic_fn(ids[:i] + ids[i + 1:]))
    return out


def bca_interval(theta_hat: float, boot_dist: list, jack_dist: list,
                 alpha: float = 0.05) -> tuple:
    """Bias-corrected and accelerated interval. Standard formula
    (Efron & Tibshirani): bias-correct via the fraction of bootstrap
    draws below theta_hat, accelerate via the jackknife's third
    moment, then map the desired alpha through both corrections."""
    boot = sorted(boot_dist)
    n_boot = len(boot)
    prop_below = sum(1 for b in boot if b < theta_hat) / n_boot
    prop_below = min(max(prop_below, 1e-6), 1 - 1e-6)  # avoid inf at 0/1
    z0 = norm.ppf(prop_below)

    jack_mean = sum(jack_dist) / len(jack_dist)
    num = sum((jack_mean - j) ** 3 for j in jack_dist)
    den = 6 * (sum((jack_mean - j) ** 2 for j in jack_dist) ** 1.5)
    a = num / den if den != 0 else 0.0

    z_lo, z_hi = norm.ppf(alpha / 2), norm.ppf(1 - alpha / 2)

    def adjust(z):
        return norm.cdf(z0 + (z0 + z) / (1 - a * (z0 + z)))

    p_lo, p_hi = adjust(z_lo), adjust(z_hi)
    p_lo, p_hi = max(0.0, min(1.0, p_lo)), max(0.0, min(1.0, p_hi))
    lo_idx = max(0, min(n_boot - 1, int(round(p_lo * n_boot))))
    hi_idx = max(0, min(n_boot - 1, int(round(p_hi * n_boot))))
    return boot[lo_idx], boot[hi_idx]


def percentile_interval(boot_dist: list, alpha: float = 0.05) -> tuple:
    """Plain percentile CI — reported alongside BCa per the spec, as a
    check that the correction isn't doing anything surprising."""
    boot = sorted(boot_dist)
    n = len(boot)
    lo = boot[max(0, int(n * alpha / 2))]
    hi = boot[min(n - 1, int(n * (1 - alpha / 2)))]
    return lo, hi
