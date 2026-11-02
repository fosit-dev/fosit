"""Placebo calibration: check the conformal ranges against fake cells over the same dates.

METHODOLOGY.md §5.6. Conformal inference (§5) assumes the gap between a cell and
its twin behaves the same in every stretch of time. With few markets (US states)
the gap wanders slowly, and the stretch at the end of the series, where the
test sits, wanders more than the middle: on synthetic state data nominal 90%
ranges held the truth only about 82-86% of the time.

So we also run the estimator on placebo cells: random sets of markets that got
no ads (the control pool; for a national holdout, other campaign markets, on the
same indexed series), each the size of the real cell, with its twin built from
the rest of the pool. Their errors over the *same* measurement window, scaled by
each twin's pre-period residual SD, show how far a twin really drifts in that
window. The reported range is the hull of the conformal range and the
placebo range (estimate ± the placebo quantile x the real twin's residual SD),
so it is never narrower than plain conformal inference.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from . import ascm
from .estimate import CellEstimate, cell_series, screen_donors, DONOR_MIN_NONZERO_SHARE
from .holdout import holdout_series
from .panel import Panel

N_PLACEBOS = 40
MIN_POOL = 6        # need at least 3 placebo markets and 3 donors


def scaled_window_error(y1: np.ndarray, Y0: np.ndarray, n_pre: int, fixed_effects: bool = True) -> float | None:
    """Mean error over the window after n_pre, divided by the pre-period residual SD (same estimator as §4)."""
    lam, _ = ascm.select_lambda(y1, Y0, n_pre, fixed_effects)
    fit = ascm.fit(y1, Y0, n_pre, lam=lam, fixed_effects=fixed_effects)
    r = y1 - fit.counterfactual
    sd = float(np.std(r[:n_pre]))
    return float(np.mean(r[n_pre:]) / sd) if sd > 0 else None


def placebo_errors(panel: Panel, kpi: str, size: int, pool, pre_cols: np.ndarray, post_cols: np.ndarray, *,
                   holdout: bool = False, n: int = N_PLACEBOS, seed: int = 0, fixed_effects: bool = True,
                   min_nonzero_share: float = DONOR_MIN_NONZERO_SHARE) -> np.ndarray:
    """Scaled window errors of `n` placebo cells of `size` markets drawn from `pool` (seeded, so reproducible)."""
    usable, _ = screen_donors(panel, kpi, sorted(pool), pre_cols, min_nonzero_share)
    if len(usable) < MIN_POOL:
        return np.array([])
    size = max(1, min(size, len(usable) // 2))
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        pick = sorted(rng.choice(usable, size, replace=False).tolist())
        rest = [g for g in usable if g not in set(pick)]
        if holdout:
            s = holdout_series(panel, kpi, pick, rest, pre_cols, post_cols, min_nonzero_share)[0]
        else:
            s = cell_series(panel, kpi, pick, rest, pre_cols, post_cols, min_nonzero_share)
        z = scaled_window_error(s.y1, s.Y0, s.n_pre, fixed_effects)
        if z is not None and math.isfinite(z):
            out.append(z)
    return np.array(out)


def quantile(z: np.ndarray, level: float) -> float:
    """Conformal quantile of |z|: the ceil((P+1) level)-th smallest, or inf when there are too few placebos."""
    a = np.sort(np.abs(z))
    k = math.ceil((len(a) + 1) * level)
    return float(a[k - 1]) if 0 < k <= len(a) else math.inf


@dataclass
class Calibration:
    n: int                      # placebos that ran
    quantiles: dict             # level -> quantile of |scaled error|
    p_value: float              # share of placebos at least as extreme as the real cell (with the +1 correction)
    widened: dict               # level -> True if the placebo range is wider than the conformal one

    def to_dict(self) -> dict:
        return {"n": self.n, "quantiles": {str(k): v for k, v in self.quantiles.items()}, "p_value": self.p_value,
                "widened": {str(k): v for k, v in self.widened.items()}}


def calibrate(est: CellEstimate, z: np.ndarray, levels) -> Calibration | None:
    """Widen est.intervals to the hull with the placebo ranges and raise its p-value to the placebo p-value (§5.6)."""
    if len(z) == 0:
        return None
    sd = float(np.std((est.observed - est.counterfactual)[: est.n_pre]))
    if sd <= 0:
        return None
    z_real = abs(est.att) / sd
    p_placebo = (1 + int(np.sum(np.abs(z) >= z_real))) / (len(z) + 1)
    quantiles, widened = {}, {}
    for lv in levels:
        q = quantile(z, lv)
        lo, hi = est.intervals[lv]
        plo, phi = est.att - q * sd, est.att + q * sd
        quantiles[lv] = q
        widened[lv] = bool(plo < lo or phi > hi)
        est.intervals[lv] = (min(lo, plo), max(hi, phi))
    est.p_value = max(est.p_value, p_placebo)
    return Calibration(len(z), quantiles, p_placebo, widened)
