"""National holdout: the campaign runs everywhere except a few held-out markets.

METHODOLOGY.md §13. With several cells (vendors that split the country, §13.7) each
cell gets its own twin of the holdout, built only from that cell's markets. The twin is built for the *holdout* (a handful of markets)
from the campaign markets (many), never the other way round: a twin of nearly
the whole country built from ten markets leans on one or two of them and its
intervals undercover badly (§13.3). Both sides are indexed to their own
pre-period average, so the twin of the holdout tracks the campaign markets'
*relative* movement. During the test the twin shows what the holdout would have
sold with the ads, and the gap is the share of the campaign markets' sales the
ads drove. That share times the campaign markets' actual sales is the
incremental total.

Same estimator, same inference, same lambda choice as a geo-cell test (§4-§5);
only the series it is given and the translation into business units differ.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .estimate import CellEstimate, CellSeries, estimate, screen_donors, DONOR_MIN_NONZERO_SHARE
from .panel import Panel


def index_rows(mat: np.ndarray, holdout_rows, donor_rows, n_base: int) -> tuple[np.ndarray, np.ndarray]:
    """Holdout's total sales and each donor's sales, each divided by its average over the first n_base days."""
    h = mat[holdout_rows].sum(axis=0)
    D = mat[donor_rows]
    return h / h[:n_base].mean(), D / D[:, :n_base].mean(axis=1, keepdims=True)


def holdout_series(panel: Panel, kpi: str, holdout_geos, campaign_geos, pre_cols: np.ndarray, post_cols: np.ndarray,
                   min_nonzero_share: float = DONOR_MIN_NONZERO_SHARE) -> tuple[CellSeries, float, np.ndarray]:
    """Indexed series for the estimator, the holdout's pre-period daily level, and the campaign markets' daily totals."""
    cols = np.concatenate([pre_cols, post_cols])
    donors, dropped = screen_donors(panel, kpi, sorted(campaign_geos), pre_cols, min_nonzero_share)
    if not donors:
        raise ValueError("No usable campaign markets to build the holdout's twin from.")
    mat = panel.kpis[kpi][:, cols]
    level = float(mat[panel.rows(holdout_geos), : len(pre_cols)].sum(axis=0).mean())
    if level <= 0:
        raise ValueError("The holdout markets have no sales in the history period.")
    y1, Y0 = index_rows(mat, panel.rows(holdout_geos), panel.rows(donors), len(pre_cols))
    campaign = mat[panel.rows(campaign_geos)].sum(axis=0)
    series = CellSeries(y1, Y0, donors, dropped, len(holdout_geos), len(pre_cols), len(post_cols), panel.dates[cols])
    return series, level, campaign


@dataclass
class HoldoutEstimate:
    """A holdout read in business units. Exposes the same interface the Read module uses for a geo cell."""

    index: CellEstimate         # holdout's sales index (observed) vs its twin built from the campaign markets
    holdout_level: float        # holdout's average daily sales in the pre-period (index 1.0)
    campaign: np.ndarray        # (T,) campaign markets' total daily sales
    n_campaign: int
    series: CellSeries | None = field(default=None, repr=False)   # the indexed inputs, for head-to-head grids

    # -- the estimator's own outputs --------------------------------------------------
    kpi = property(lambda s: s.index.kpi)
    n_pre = property(lambda s: s.index.n_pre)
    n_post = property(lambda s: s.index.n_post)
    lam = property(lambda s: s.index.lam)
    att = property(lambda s: s.index.att)
    p_value = property(lambda s: s.index.p_value)
    pre_fit_nrmse = property(lambda s: s.index.pre_fit_nrmse)
    weights = property(lambda s: s.index.weights)
    dropped_donors = property(lambda s: s.index.dropped_donors)
    dates = property(lambda s: s.index.dates)
    evaluated = property(lambda s: s.index.evaluated)

    # -- translation (§13.4) ---------------------------------------------------------
    @property
    def twin_post(self) -> float:
        return float(self.index.counterfactual[self.n_pre:].sum())

    def ads_share(self, tau: float) -> float:
        """Share of the campaign markets' sales the ads drove, if the holdout's index sat tau below its twin each day."""
        return -tau * self.n_post / self.twin_post

    @property
    def scale(self) -> float:
        """Incremental total per unit of tau (linear), so head-to-head grids map like a geo cell's (§7.2)."""
        return -self.n_post * self.campaign_total / self.twin_post

    @property
    def campaign_total(self) -> float:
        return float(self.campaign[self.n_pre:].sum())

    @property
    def incremental(self) -> float:
        return self.ads_share(self.att) * self.campaign_total

    def incremental_interval(self, level: float) -> tuple[float, float]:
        lo, hi = self.index.intervals[level]
        # ads_share is decreasing in tau: the high tau gives the low incremental
        return self.ads_share(hi) * self.campaign_total, self.ads_share(lo) * self.campaign_total

    @property
    def observed_total(self) -> float:
        return self.campaign_total

    @property
    def counterfactual_total(self) -> float:
        return self.campaign_total - self.incremental

    @property
    def lift(self) -> float:
        return self.incremental / self.counterfactual_total

    def test_counterfactual(self, test_days: int) -> float:
        """Campaign markets' sales without ads over the ads-on days, for the meaningful effect (§8)."""
        return float(self.campaign[self.n_pre:self.n_pre + test_days].sum() * (1 - self.ads_share(self.att)))

    def chart(self) -> dict:
        """The holdout's actual sales and its twin (what it would have sold with the ads), in sales units."""
        return {"observed": (self.index.observed * self.holdout_level).round(2).tolist(),
                "counterfactual": (self.index.counterfactual * self.holdout_level).round(2).tolist(),
                "role": "holdout"}


def estimate_holdout(panel: Panel, kpi: str, holdout_geos, campaign_geos, pre_cols, post_cols,
                     statistic: str = "abs_sum", levels=(0.90, 0.95), fixed_effects: bool = True, perms=None,
                     min_nonzero_share: float = DONOR_MIN_NONZERO_SHARE) -> HoldoutEstimate:
    series, level, campaign = holdout_series(panel, kpi, holdout_geos, campaign_geos, pre_cols, post_cols, min_nonzero_share)
    kw = {} if perms is None else {"perms": perms}
    est = estimate(series, statistic, levels, fixed_effects, kpi=kpi, **kw)
    return HoldoutEstimate(est, level, campaign, len(campaign_geos), series)
