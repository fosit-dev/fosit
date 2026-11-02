"""Conformal inference for synthetic controls: p-values, intervals, joint regions.

METHODOLOGY.md §5 (per cell) and §7.2 (head-to-head). Reference: Chernozhukov,
Wüthrich & Zhu (2021), "An Exact and Robust Conformal Inference Method for
Counterfactual and Synthetic Controls", JASA 116(536).

Hypotheses are about tau0: a constant daily effect on the *average* treated geo
over the measurement window (the last n_post periods of the series).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from . import ascm

# abs_sum  |sum of window residuals|: tests the average effect (FOSIT default, METHODOLOGY.md §5.1)
# sum_abs  sum of |window residuals|: the q=1 statistic of Chernozhukov et al. and GeoLift's
#          two-sided "Total" test; it tests a zero effect on every day, so it has less power
#          against a steady lift. Available for comparison with GeoLift (§12).
STATISTICS = ("abs_sum", "sum_abs", "positive_sum", "negative_sum")
_TIE_TOL = 1e-9


@dataclass(frozen=True)
class Permutations:
    """How residuals are permuted over time (§5.1 step 5).

    "moving_block": every circular shift of the series (T permutations, deterministic).
        Keeps autocorrelation intact; valid under weak dependence.
    "iid": `n` random reorderings drawn from `seed`. More power, but assumes
        residuals are exchangeable across days. The same draws are reused for
        every hypothesis so p(tau0) is a smooth function of tau0.
    """

    kind: str = "moving_block"
    n: int = 1000
    seed: int = 0

    def window_sums(self, u: np.ndarray, n_post: int) -> np.ndarray:
        """Window sums under each permutation; element 0 is always the observed sum."""
        if self.kind == "moving_block":
            return shifted_window_sums(u, n_post)
        if self.kind == "iid":
            idx = _iid_index(len(u), n_post, self.n, self.seed)
            return np.concatenate([[u[-n_post:].sum()], u[idx].sum(axis=1)])
        raise ValueError(f"unknown permutation kind {self.kind!r}")


BLOCK = Permutations("moving_block")


@lru_cache(maxsize=32)
def _iid_index(T: int, n_post: int, n: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.argsort(rng.random((n, T)), axis=1)[:, :n_post]


def null_residuals(y1: np.ndarray, Y0: np.ndarray, n_post: int, tau0: float, lam: float,
                   fixed_effects: bool = True) -> np.ndarray:
    """Residuals over all T periods after removing tau0 from the window and refitting (§5.1 steps 1-3).

    lambda stays fixed at the value chosen on the pre-period; only weights are refit.
    """
    T = len(y1)
    adjusted = y1.astype(float).copy()
    adjusted[T - n_post:] -= tau0
    refit = ascm.fit(adjusted, Y0, n_fit=T, lam=lam, fixed_effects=fixed_effects)
    return refit.residuals(adjusted)


def shifted_window_sums(u: np.ndarray, n_post: int) -> np.ndarray:
    """Sum of residuals over the window under every circular time shift (§5.1 step 5).

    Element j is sum_{t in window} u[(t + j) mod T]; element 0 is the observed sum.
    """
    T = len(u)
    doubled = np.concatenate([[0.0], np.cumsum(np.concatenate([u, u]))])
    starts = np.arange(T) + (T - n_post)
    return doubled[starts + n_post] - doubled[starts]


def _stat(sums: np.ndarray, statistic: str) -> np.ndarray:
    if statistic == "abs_sum":
        return np.abs(sums)
    if statistic == "positive_sum":
        return sums
    if statistic == "negative_sum":
        return -sums
    raise ValueError(f"unknown statistic {statistic!r}")


def p_value_from_residuals(u: np.ndarray, n_post: int, statistic: str = "abs_sum",
                           perms: Permutations = BLOCK) -> float:
    """Share of permutations whose statistic is at least the observed one (§5.1 step 6)."""
    if statistic == "sum_abs":
        s = perms.window_sums(np.abs(u), n_post)
    else:
        s = _stat(perms.window_sums(u, n_post), statistic)
    tol = _TIE_TOL * max(1.0, float(np.max(np.abs(s))))
    return float(np.mean(s >= s[0] - tol))


def p_value(y1, Y0, n_post, tau0, lam, statistic="abs_sum", fixed_effects=True, perms: Permutations = BLOCK) -> float:
    return p_value_from_residuals(null_residuals(y1, Y0, n_post, tau0, lam, fixed_effects), n_post, statistic, perms)


@dataclass
class Interval:
    level: float
    low: float           # -inf / +inf when unbounded in the searched range
    high: float
    note: str = ""


def invert_test(y1, Y0, n_post, lam, tau_hat, scale, levels=(0.90, 0.95), statistic="abs_sum",
                fixed_effects=True, perms: Permutations = BLOCK, max_expand=12, rel_tol=0.005, max_bisect=30) -> tuple[dict[float, Interval], list]:
    """Confidence intervals by test inversion: the set of tau0 not rejected at each level (§5.2).

    Starting from the point estimate tau_hat we step outward (doubling the step)
    until the test rejects at the strictest level, then bisect each endpoint.
    `scale` sets the first step (we use the pre-period residual SD / sqrt(n_post)).
    Returns ({level: Interval}, evaluated [(tau0, p)] points).
    """
    cache: dict[float, float] = {}

    def p(tau0: float) -> float:
        if tau0 not in cache:
            cache[tau0] = p_value(y1, Y0, n_post, tau0, lam, statistic, fixed_effects, perms)
        return cache[tau0]

    step0 = max(abs(scale), 1e-9 * max(1.0, abs(tau_hat)))

    def accepted_point(alpha: float) -> float | None:
        """tau_hat if it is not rejected, else the nearest scanned point that isn't (rare: very poor fit)."""
        if p(tau_hat) > alpha:
            return tau_hat
        for k in range(1, 9):
            for cand in (tau_hat - k * step0, tau_hat + k * step0):
                if p(cand) > alpha:
                    return cand
        return None

    one_sided_low = statistic == "positive_sum"
    one_sided_high = statistic == "negative_sum"
    out: dict[float, Interval] = {}
    for lv in sorted(levels, reverse=True):
        alpha = round(1.0 - lv, 12)  # 1 - 0.90 is 0.0999...98 in floating point
        centre = accepted_point(alpha)
        if centre is None:
            out[lv] = Interval(lv, float("nan"), float("nan"), "empty: no effect size is consistent with the data")
            continue
        bounds = []
        for direction in (-1, 1):
            if (direction == 1 and one_sided_low) or (direction == -1 and one_sided_high):
                bounds.append(direction * float("inf"))
                continue
            inside, step, outside = centre, step0, None
            for _ in range(max_expand):
                cand = centre + direction * step
                if p(cand) <= alpha:
                    outside = cand
                    break
                inside, step = cand, step * 2
            if outside is None:
                bounds.append(direction * float("inf"))
                continue
            tol = rel_tol * max(abs(outside - centre), step0)
            for _ in range(max_bisect):
                if abs(outside - inside) <= tol:
                    break
                mid = 0.5 * (inside + outside)
                if p(mid) > alpha:
                    inside = mid
                else:
                    outside = mid
            bounds.append(inside)
        note = "" if all(np.isfinite(bounds)) else "unbounded within the searched range"
        out[lv] = Interval(lv, bounds[0], bounds[1], note)
    return out, sorted(cache.items())


@dataclass
class CellGrid:
    """Residual window-sums for one cell over a grid of hypothesised effects, for joint inference."""

    taus: np.ndarray           # (G,)
    sums: np.ndarray           # (G, T) shifted window sums
    sigma: np.ndarray          # (G,) full-sample residual SD under each hypothesis


def cell_grid(y1, Y0, n_post, lam, low, high, n=41, fixed_effects=True, perms: Permutations = BLOCK) -> CellGrid:
    taus = np.linspace(low, high, n)
    sums, sig = [], []
    for t in taus:
        u = null_residuals(y1, Y0, n_post, float(t), lam, fixed_effects)
        sums.append(perms.window_sums(u, n_post))
        sig.append(float(np.std(u)) or 1.0)
    return CellGrid(taus, np.array(sums), np.array(sig))


def joint_p_values(a: CellGrid, b: CellGrid) -> np.ndarray:
    """p-value for every (tau_a, tau_b) pair under a common time shift (§7.2 steps 2-3).

    Statistic: max of the two cells' |window sum| / residual SD. The same permutation
    is applied to both cells so their correlation (shared days, shared controls) is
    kept; both grids must therefore be built with the same Permutations.
    Returns a (G_a, G_b) array.
    """
    A = np.abs(a.sums) / a.sigma[:, None]
    B = np.abs(b.sums) / b.sigma[:, None]
    M = np.maximum(A[:, None, :], B[None, :, :])
    tol = _TIE_TOL * max(1.0, float(M.max()))
    return np.mean(M >= M[:, :, :1] - tol, axis=2)


def project(region: np.ndarray, a_vals: np.ndarray, b_vals: np.ndarray, f) -> tuple[float, float]:
    """[min, max] of f(a, b) over grid points inside the joint region (§7.2 step 5).

    a_vals / b_vals are the business quantities (e.g. incremental orders) at each
    grid tau. f must accept numpy arrays and may return nan/inf where undefined.
    Returns (nan, nan) if the region is empty.
    """
    ia, ib = np.nonzero(region)
    if len(ia) == 0:
        return float("nan"), float("nan")
    with np.errstate(divide="ignore", invalid="ignore"):
        vals = f(a_vals[ia], b_vals[ib])
    if np.any(np.isnan(vals)):
        return float("nan"), float("nan")
    return float(np.min(vals)), float(np.max(vals))
