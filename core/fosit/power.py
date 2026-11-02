"""Power simulation: minimum detectable effect by cell and test length, and what it means in money.

METHODOLOGY.md §10. For each placebo window in the history we inject a known
lift into the cell's geos during the test days (none during cooldown), run the
same estimator and test that the real read will use, and count detections.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.stats import binom

from . import ascm, conformal
from .estimate import cell_series
from .holdout import holdout_series
from .panel import Panel
from .placebo import placebo_errors, quantile

COARSE_EFFECTS = (0.025, 0.05, 0.10, 0.15, 0.20, 0.30, 0.50)
SPARE_DAYS = 42   # history kept free for placebo windows: 7 windows at 7-day steps
BASELINE_DAYS = 28


@dataclass
class PowerConfig:
    kpi: str = "orders"
    pre_days: int = 84
    durations: tuple = (21, 28, 42, 56)     # test days to compare
    cooldown_days: int = 7
    alpha: float = 0.10
    statistic: str = "abs_sum"
    permutations: conformal.Permutations = field(default_factory=conformal.Permutations)
    power_target: float = 0.80
    n_windows: int = 10
    window_step: int = 7
    bisect_steps: int = 3
    fixed_effects: bool = True
    donor_min_nonzero_share: float = 0.5
    # If True, each test length uses the longest pre-period (up to pre_days) that still leaves
    # SPARE_DAYS of history for placebo windows, never below 8 weeks (METHODOLOGY.md §10.1).
    adaptive_pre: bool = False
    # National holdout (§13): the cell is the campaign's markets, the control is the holdout, and
    # the lift is injected into the campaign markets, which are the holdout twin's donors.
    holdout: bool = False
    # Placebo calibration (§5.6): a detection must also clear the placebo range, so the MDE matches the Read module.
    placebos: int = 0
    seed: int = 0


def simulation_pre_days(cfg: PowerConfig, n_days: int, n_post: int) -> int:
    if not cfg.adaptive_pre:
        return cfg.pre_days
    return max(56, min(cfg.pre_days, n_days - n_post - SPARE_DAYS))


def calibration_flag(false_positives: int, windows: int, alpha: float, level: float = 0.05) -> bool:
    """True if this many false positives would be surprising for a calibrated test (one-sided binomial test, §10.1 step 7)."""
    if windows == 0 or false_positives == 0:
        return False
    return float(binom.sf(false_positives - 1, windows, alpha)) < level


@dataclass
class _Window:
    y1: np.ndarray
    Y0: np.ndarray
    lam: float
    pre_cf: np.ndarray          # counterfactual from the pre-period fit, before any injected lift
    n_post: int
    test_days: int
    weights: np.ndarray | None = None   # holdout only: the twin moves with lift injected into its donors


def placebo_starts(n_days: int, pre_days: int, window_len: int, n_windows: int, step: int) -> list[int]:
    """Start indices of placebo windows, latest first, each with a full pre-period before it (§10.1 step 1)."""
    starts, s = [], n_days - window_len
    while s - pre_days >= 0 and len(starts) < n_windows:
        starts.append(s)
        s -= step
    return starts


class PowerSimulator:
    def __init__(self, panel: Panel, cells: list[list[str]], control: list[str], cfg: PowerConfig):
        self.panel, self.cells, self.control, self.cfg = panel, cells, control, cfg

    def _windows(self, cell: list[str], test_days: int) -> list[_Window]:
        cfg = self.cfg
        n_post = test_days + cfg.cooldown_days
        pre_days = simulation_pre_days(cfg, self.panel.n_days, n_post)
        out = []
        for s in placebo_starts(self.panel.n_days, pre_days, n_post, cfg.n_windows, cfg.window_step):
            pre_cols, post_cols = np.arange(s - pre_days, s), np.arange(s, s + n_post)
            if cfg.holdout:
                series = holdout_series(self.panel, cfg.kpi, self.control, cell, pre_cols, post_cols, cfg.donor_min_nonzero_share)[0]
            else:
                series = cell_series(self.panel, cfg.kpi, cell, self.control, pre_cols, post_cols, cfg.donor_min_nonzero_share)
            lam, _ = ascm.select_lambda(series.y1, series.Y0, pre_days, cfg.fixed_effects)
            pre = ascm.fit(series.y1, series.Y0, pre_days, lam=lam, fixed_effects=cfg.fixed_effects)
            out.append(_Window(series.y1, series.Y0, lam, pre.counterfactual, n_post, test_days,
                               pre.weights if cfg.holdout else None))
        return out

    def _placebo_q(self, cell: list[str], test_days: int) -> float:
        """Placebo quantile for the latest window (§5.6); 0 = no placebo requirement."""
        cfg = self.cfg
        if not cfg.placebos:
            return 0.0
        n_post = test_days + cfg.cooldown_days
        pre_days = simulation_pre_days(cfg, self.panel.n_days, n_post)
        starts = placebo_starts(self.panel.n_days, pre_days, n_post, 1, cfg.window_step)
        if not starts:
            return 0.0
        s = starts[0]
        size, pool = (len(self.control), cell) if cfg.holdout else (len(cell), self.control)
        z = placebo_errors(self.panel, cfg.kpi, size, pool, np.arange(s - pre_days, s), np.arange(s, s + n_post),
                           holdout=cfg.holdout, n=cfg.placebos, seed=[cfg.seed, test_days, len(cell)],
                           fixed_effects=cfg.fixed_effects, min_nonzero_share=cfg.donor_min_nonzero_share)
        return quantile(z, 1 - cfg.alpha) if len(z) else 0.0

    def _detected(self, w: _Window, effect: float, q: float = 0.0) -> bool:
        cfg = self.cfg
        y, Y0 = w.y1.copy(), w.Y0
        first = len(y) - w.n_post
        days = slice(first, first + w.test_days)
        if w.weights is None:
            y[days] *= 1 + effect
            cf = w.pre_cf
        else:
            # Holdout: the campaign markets (the twin's donors) get the lift, so the twin rises above the holdout
            Y0 = Y0.copy()
            Y0[:, days] *= 1 + effect
            cf = w.pre_cf + w.weights @ (Y0 - w.Y0)
        att = float(np.mean(y[first:] - cf[first:]))
        sign = -1 if w.weights is not None else 1
        if effect > 0 and sign * att <= 0:
            return False
        if q > 0:
            first_pre = len(y) - w.n_post
            sd = float(np.std((w.y1 - w.pre_cf)[:first_pre]))
            if sd <= 0 or abs(att) <= q * sd:
                return False
        p = conformal.p_value(y, Y0, w.n_post, 0.0, w.lam, cfg.statistic, cfg.fixed_effects, cfg.permutations)
        return p <= cfg.alpha

    def _power(self, windows: list[_Window], effect: float, q: float = 0.0) -> float:
        return float(np.mean([self._detected(w, effect, q) for w in windows]))

    def curve(self, cell: list[str], test_days: int) -> dict:
        """Power at 0 (false-positive rate), the coarse grid, and a bisection around the target crossing."""
        cfg = self.cfg
        windows = self._windows(cell, test_days)
        if not windows:
            return {"test_days": test_days, "windows": 0, "points": [], "mde": None,
                    "note": "History too short for any placebo window of this length."}
        q = self._placebo_q(cell, test_days)
        points = {0.0: self._power(windows, 0.0, q)}
        crossing = None
        for e in COARSE_EFFECTS:
            points[e] = self._power(windows, e, q)
            if points[e] >= cfg.power_target:
                crossing = e
                break
        mde = None
        if crossing is not None:
            prev = max(k for k in points if k < crossing)
            lo, hi = prev, crossing
            for _ in range(cfg.bisect_steps):
                mid = round((lo + hi) / 2, 4)
                points[mid] = self._power(windows, mid, q)
                lo, hi = (mid, hi) if points[mid] < cfg.power_target else (lo, mid)
            mde = hi
        y_recent = self.panel.kpis[cfg.kpi][self.panel.rows(cell), -BASELINE_DAYS:].sum(axis=0).mean()
        return {
            "test_days": test_days,
            "pre_days": simulation_pre_days(cfg, self.panel.n_days, test_days + cfg.cooldown_days),
            "windows": len(windows),
            "placebo_quantile": q or None,
            "points": [{"effect": k, "power": v} for k, v in sorted(points.items())],
            "mde": mde,
            "false_positive_rate": points[0.0],
            "calibration_flag": calibration_flag(round(points[0.0] * len(windows)), len(windows), cfg.alpha),
            "baseline_daily": float(y_recent),
            "baseline_test_total": float(y_recent * test_days),
            "note": "" if mde is not None else f"Above {COARSE_EFFECTS[-1]:.0%}: not detectable with this design.",
        }

    def run(self, progress=None) -> list[dict]:
        out = []
        total = len(self.cells) * len(self.cfg.durations)
        for c, cell in enumerate(self.cells):
            curves = []
            for d, days in enumerate(self.cfg.durations):
                curves.append(self.curve(cell, days))
                if progress:
                    progress({"stage": "power", "done": c * len(self.cfg.durations) + d + 1, "total": total})
            out.append({"cell_index": c, "curves": curves})
        return out


def money(curve: dict, budget: float, kpi: str = "orders") -> dict:
    """Translate an MDE into the iCPA (or iROAS) a vendor would need for the test to see it (§10.2)."""
    if not curve.get("mde"):
        return {"mde_units": None, "detectable_icpa": None, "detectable_iroas": None}
    units = curve["mde"] * curve["baseline_test_total"]
    return {
        "mde_units": units,
        "detectable_icpa": budget / units if kpi == "orders" and units > 0 else None,
        "detectable_iroas": units / budget if kpi == "revenue" and budget > 0 else None,
    }


def power_at_budget(curve: dict, budget: float, true_icpa: float) -> float | None:
    """Power if incremental orders = budget / true_icpa (linear response, §10.2), interpolated on the curve."""
    if not curve.get("points") or true_icpa <= 0 or curve["baseline_test_total"] <= 0:
        return None
    effect = (budget / true_icpa) / curve["baseline_test_total"]
    xs = [p["effect"] for p in curve["points"]]
    ys = [p["power"] for p in curve["points"]]
    return float(np.interp(effect, xs, ys))
