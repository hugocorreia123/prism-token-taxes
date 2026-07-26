"""GLM layer: negative-binomial (tokens) and logistic (accuracy),
fixed effects S x B x L full factorial, via statsmodels — a mature,
independently-tested library, not a hand-rolled implementation of
something this consequential.

Design note (deviation from the spec's literal "GLMM with random
intercept"): a true mixed negative-binomial model has no mature,
well-tested pure-Python implementation without an R dependency. Fixed-
effects GLM + cluster bootstrap (bootstrap.py) achieves the same
practical goal — valid inference that respects task-level clustering —
without depending on a random-effects distributional assumption the
GLM itself would need to get right. The cluster bootstrap, not the
GLM's own standard errors, is what produces every reported CI.
"""
from __future__ import annotations

import statsmodels.api as sm
import statsmodels.formula.api as smf


def fit_token_glm(df):
    """Negative-binomial, tokens ~ S * B * L (full factorial), with the
    dispersion parameter (alpha) estimated by MLE — NOT statsmodels'
    GLM default of a fixed alpha=1.0, which silently mis-fits real
    overdispersion and would understate every downstream CI."""
    return smf.negativebinomial("tokens ~ S * B * L", data=df).fit(disp=0)


def fit_accuracy_glm(df):
    """Logistic GLM: success ~ S * B * L (full factorial).

    CRITICAL: `success` is coerced to explicit int (0/1) here, never
    left as bool. A real bug, caught by the synthetic-recovery test
    before this ever touched real data: patsy/statsmodels silently
    treats a bool response column as 2-level categorical and fits the
    WRONG reference level — a planted true P(success)=0.80 came back
    as a fitted 0.20, an exact inversion. Explicit int encoding is not
    optional style; it is the fix."""
    df = df.copy()
    df["success"] = df["success"].astype(int)
    return smf.glm("success ~ S * B * L", data=df,
                   family=sm.families.Binomial()).fit()


def marginal_prediction(model, S: int, B: int, L: int) -> float:
    """Predicted mean at one cell, on the response scale (tokens or
    probability, depending on which model was fit)."""
    import pandas as pd
    row = pd.DataFrame({"S": [S], "B": [B], "L": [L]})
    return float(model.predict(row).iloc[0])
