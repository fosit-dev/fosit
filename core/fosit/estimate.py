"""Per-cell estimation: fit, inference and incremental totals.

METHODOLOGY.md §4 (estimator), §5 (inference), §6 (business metrics, the parts
that don't need spend). The Read module and the power simulation both call
`cell_series`, so planning and reading use exactly the same estimator.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import ascm, conformal
from .panel import Panel

DONOR_MIN_NONZERO_SHARE = 0.5


@dataclass
class CellSeries:
    """Inputs to the estimator for one cell and one KPI."""

    y1: np.ndarray            # (T,) average across the cell's geos
    Y0: np.ndarray            # (J, T) donor geos
    donors: list[str]
    dropped_donors: list[str]
    n_geos: int
    n_pre: int
    n_post: int
    dates: pd.DatetimeIndex


def screen_donors(panel: Panel, kpi: str, donor_geos, pre_cols: np.ndarray,
                  min_nonzero_share: float = DONOR_MIN_NONZERO_SHARE) -> tuple[list[str], list[str]]:
    """Drop donors with zero KPI on more than half the pre-period days (§3 step 5)."""
    rows = panel.rows(donor_geos)
    nonzero = (panel.kpis[kpi][np.ix_(rows, pre_cols)] != 0).mean(axis=1)
    keep = [g for g, s in zip(donor_geos, nonzero) if s >= min_nonzero_share]
    drop = [g for g, s in zip(donor_geos, nonzero) if s < min_nonzero_share]
    return keep, drop


def cell_series(panel: Panel, kpi: str, cell_geos, donor_geos, pre_cols: np.ndarray, post_cols: np.ndarray,
                min_nonzero_share: float = DONOR_MIN_NONZERO_SHARE) -> CellSeries:
    """Assemble y1 / Y0 for the given pre-period and measurement-window column indices."""
    cols = np.concatenate([pre_cols, post_cols])
    donors, dropped = screen_donors(panel, kpi, sorted(donor_geos), pre_cols, min_nonzero_share)
    if not donors:
        raise ValueError("No usable control geos: every donor was screened out.")
    mat = panel.kpis[kpi]
    y1 = mat[np.ix_(panel.rows(cell_geos), cols)].mean(axis=0)
    Y0 = mat[np.ix_(panel.rows(donors), cols)]
    return CellSeries(y1, Y0, donors, dropped, len(cell_geos), len(pre_cols), len(post_cols), panel.dates[cols])


@dataclass
class CellEstimate:
    kpi: str
    n_geos: int
    n_pre: int
    n_post: int
    lam: float
    att: float                          # average daily effect on the average treated geo
    p_value: float
    intervals: dict                     # level -> (low, high) for att
    pre_fit_nrmse: float
    observed: np.ndarray                # (T,) average treated series
    counterfactual: np.ndarray          # (T,)
    weights: dict                       # donor geo -> augmented weight
    dropped_donors: list
    dates: pd.DatetimeIndex
    evaluated: list = field(default_factory=list)

    # §6 totals: multiply per-geo daily quantities by n_geos x n_post
    @property
    def scale(self) -> float:
        return float(self.n_geos * self.n_post)

    @property
    def incremental(self) -> float:
        return self.att * self.scale

    def incremental_interval(self, level: float) -> tuple[float, float]:
        lo, hi = self.intervals[level]
        return lo * self.scale, hi * self.scale

    @property
    def counterfactual_total(self) -> float:
        return float(self.counterfactual[self.n_pre:].sum() * self.n_geos)

    @property
    def observed_total(self) -> float:
        return float(self.observed[self.n_pre:].sum() * self.n_geos)

    @property
    def lift(self) -> float:
        return self.incremental / self.counterfactual_total

    def lift_interval(self, level: float) -> tuple[float, float]:
        lo, hi = self.incremental_interval(level)
        return lo / self.counterfactual_total, hi / self.counterfactual_total

    def test_counterfactual(self, test_days: int) -> float:
        """Twin's total over the ads-on days, for the meaningful effect (§8)."""
        return float(self.counterfactual[self.n_pre:self.n_pre + test_days].sum() * self.n_geos)

    def chart(self) -> dict:
        return {"observed": (self.observed * self.n_geos).round(2).tolist(),
                "counterfactual": (self.counterfactual * self.n_geos).round(2).tolist(), "role": "cell"}


def estimate(series: CellSeries, statistic: str = "abs_sum", levels=(0.90, 0.95),
             fixed_effects: bool = True, lam: float | None = None, kpi: str = "",
             perms: conformal.Permutations = conformal.BLOCK) -> CellEstimate:
    """Point estimate, p-value and intervals for one cell (§4-§5)."""
    s = series
    if lam is None:
        lam, _ = ascm.select_lambda(s.y1[: s.n_pre], s.Y0[:, : s.n_pre], s.n_pre, fixed_effects)
    pre = ascm.fit(s.y1, s.Y0, s.n_pre, lam=lam, fixed_effects=fixed_effects)
    resid = pre.residuals(s.y1)
    att = float(resid[s.n_pre:].mean())
    p0 = conformal.p_value(s.y1, s.Y0, s.n_post, 0.0, lam, statistic, fixed_effects, perms)
    scale = float(np.std(resid[: s.n_pre])) / np.sqrt(s.n_post)
    intervals, evaluated = conformal.invert_test(s.y1, s.Y0, s.n_post, lam, att, scale, levels, statistic,
                                                fixed_effects, perms)
    return CellEstimate(
        kpi=kpi, n_geos=s.n_geos, n_pre=s.n_pre, n_post=s.n_post, lam=lam, att=att, p_value=p0,
        intervals={lv: (iv.low, iv.high) for lv, iv in intervals.items()},
        pre_fit_nrmse=pre.fit_nrmse(s.y1), observed=s.y1, counterfactual=pre.counterfactual,
        weights=dict(zip(s.donors, pre.weights.tolist())), dropped_donors=s.dropped_donors, dates=s.dates,
        evaluated=evaluated,
    )
