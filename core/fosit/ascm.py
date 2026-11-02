"""Ridge-augmented synthetic control (ASCM) with unit fixed effects.

METHODOLOGY.md §4. Reference: Ben-Michael, Feller & Rothstein (2021),
"The Augmented Synthetic Control Method", JASA 116(536).

Shapes used throughout:
    y1  (T,)    the treated series: average KPI across the cell's geos
    Y0  (J, T)  donor series: one row per control geo
    n_fit       number of leading periods used to fit weights (the pre-period;
                all T periods during conformal refits, see conformal.py)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import nnls

LAMBDA_GRID_SIZE = 20
LAMBDA_MIN_RATIO = 1e-8
SUM_TO_ONE_PENALTY = 1e3


@dataclass(frozen=True)
class AscmFit:
    weights: np.ndarray          # augmented donor weights (J,), sum to 1, may be negative
    scm_weights: np.ndarray      # synthetic-control weights (J,), on the simplex
    lam: float                   # ridge penalty used
    counterfactual: np.ndarray   # (T,) estimate of the treated series without treatment
    n_fit: int

    def residuals(self, y1: np.ndarray) -> np.ndarray:
        return y1 - self.counterfactual

    def fit_nrmse(self, y1: np.ndarray) -> float:
        """Pre-period fit error, METHODOLOGY.md §4.5: RMSE over fit periods / mean treated level."""
        r = self.residuals(y1)[: self.n_fit]
        level = float(np.mean(y1[: self.n_fit]))
        return float(np.sqrt(np.mean(r**2)) / level) if level > 0 else float("inf")


def scm_weights(x1: np.ndarray, X0: np.ndarray) -> np.ndarray:
    """Synthetic-control weights: argmin ||x1 - X0' w||^2 over the simplex (§4.2).

    Solved as non-negative least squares (Lawson-Hanson active set) with the
    sum-to-one constraint enforced by one heavily weighted extra row. The data
    are rescaled first so the penalty dominates regardless of KPI units.
    """
    J = X0.shape[0]
    if J == 1:
        return np.ones(1)
    scale = float(np.mean(np.abs(X0))) or 1.0
    A = np.vstack([X0.T / scale, np.full((1, J), SUM_TO_ONE_PENALTY)])
    b = np.concatenate([x1 / scale, [SUM_TO_ONE_PENALTY]])
    w, _ = nnls(A, b, maxiter=max(50 * J, 500))
    s = w.sum()
    return w / s if s > 0 else np.full(J, 1.0 / J)


def ridge_adjustment(imbalance: np.ndarray, X0c: np.ndarray, lam: float) -> np.ndarray:
    """Ridge augmentation term X0c (X0c' X0c + lam I)^-1 imbalance (§4.3).

    X0c are the donors' pre-period series centred across donors, so the
    adjustment sums to zero and augmented weights still sum to one.
    """
    T0 = X0c.shape[1]
    gram = X0c.T @ X0c + lam * np.eye(T0)
    return X0c @ np.linalg.solve(gram, imbalance)


def lambda_grid(X0c: np.ndarray, n: int = LAMBDA_GRID_SIZE, min_ratio: float = LAMBDA_MIN_RATIO) -> np.ndarray:
    """Geometric grid from the largest squared singular value of X0c downward (as in augsynth)."""
    top = float(np.linalg.norm(X0c, 2) ** 2) or 1.0
    return top * np.logspace(0, np.log10(min_ratio), n)


def _demean(y1: np.ndarray, Y0: np.ndarray, n_fit: int, fixed_effects: bool):
    if not fixed_effects:
        return y1, Y0, 0.0, np.zeros(Y0.shape[0])
    m1 = float(np.mean(y1[:n_fit]))
    m0 = Y0[:, :n_fit].mean(axis=1)
    return y1 - m1, Y0 - m0[:, None], m1, m0


def _augmented(x1: np.ndarray, X0: np.ndarray, lam: float, w_scm: np.ndarray | None = None):
    if w_scm is None:
        w_scm = scm_weights(x1, X0)
    X0c = X0 - X0.mean(axis=0, keepdims=True)
    imbalance = x1 - X0.T @ w_scm
    return w_scm + ridge_adjustment(imbalance, X0c, lam), w_scm


def select_lambda(y1: np.ndarray, Y0: np.ndarray, n_fit: int, fixed_effects: bool = True,
                  fold_len: int = 7, n_folds: int = 5, min_train: int = 28) -> tuple[float, dict]:
    """Choose the ridge penalty by time-series cross-validation with the 1-SE rule (§4.3).

    The last `n_folds` blocks of `fold_len` pre-period days are held out one at a
    time; weights are fitted on all pre-period days before the block and used to
    forecast it. We take the largest lambda whose mean held-out error is within
    one standard error of the minimum.
    """
    folds = []
    for f in range(n_folds):
        end = n_fit - f * fold_len
        start = end - fold_len
        if start < min_train:
            break
        folds.append((start, end))
    _, X0_full, _, _ = _demean(y1, Y0, n_fit, fixed_effects)
    grid = lambda_grid(X0_full[:, :n_fit] - X0_full[:, :n_fit].mean(axis=0, keepdims=True))
    if not folds:
        return float(grid[len(grid) // 2]), {"grid": grid.tolist(), "errors": None, "folds": 0}

    errors = np.zeros((len(folds), len(grid)))
    for i, (start, end) in enumerate(folds):
        y, Y = y1[:end], Y0[:, :end]
        yd, Yd, _, _ = _demean(y, Y, start, fixed_effects)
        x1, X0 = yd[:start], Yd[:, :start]
        w_scm = scm_weights(x1, X0)
        X0c = X0 - X0.mean(axis=0, keepdims=True)
        imbalance = x1 - X0.T @ w_scm
        # one eigendecomposition serves every lambda on the grid
        evals, evecs = np.linalg.eigh(X0c.T @ X0c)
        proj = evecs.T @ imbalance
        held = Yd[:, start:end]
        base = held.T @ w_scm
        for j, lam in enumerate(grid):
            adj = X0c @ (evecs @ (proj / (evals + lam)))
            pred = base + held.T @ adj
            errors[i, j] = np.mean((yd[start:end] - pred) ** 2)

    mean = errors.mean(axis=0)
    se = errors.std(axis=0, ddof=1) / np.sqrt(len(folds)) if len(folds) > 1 else np.zeros_like(mean)
    best = int(np.argmin(mean))
    ok = np.nonzero(mean <= mean[best] + se[best])[0]
    chosen = int(ok.min())  # grid is descending, so the smallest index is the largest lambda
    return float(grid[chosen]), {"grid": grid.tolist(), "errors": mean.tolist(), "se": se.tolist(),
                                 "chosen_index": chosen, "folds": len(folds)}


def fit(y1: np.ndarray, Y0: np.ndarray, n_fit: int, lam: float | None = None,
        fixed_effects: bool = True, augment: bool = True) -> AscmFit:
    """Fit ASCM weights on the first `n_fit` periods and return the counterfactual for all periods (§4.4).

    lam=None selects the penalty by cross-validation; augment=False gives plain
    (fixed-effects) synthetic control, used for fast screening in market selection.
    """
    y1 = np.asarray(y1, dtype=float)
    Y0 = np.asarray(Y0, dtype=float)
    yd, Yd, m1, _ = _demean(y1, Y0, n_fit, fixed_effects)
    x1, X0 = yd[:n_fit], Yd[:, :n_fit]
    if augment:
        if lam is None:
            lam, _ = select_lambda(y1, Y0, n_fit, fixed_effects)
        w, w_scm = _augmented(x1, X0, lam)
    else:
        w_scm = scm_weights(x1, X0)
        w, lam = w_scm, float("inf")
    counterfactual = m1 + Yd.T @ w
    return AscmFit(w, w_scm, float(lam), counterfactual, n_fit)
