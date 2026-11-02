"""ASCM estimator vs independent reference computations (METHODOLOGY.md §4)."""
import unittest

import numpy as np
from scipy.optimize import minimize

from tests import _util  # noqa: F401
from fosit import ascm


def reference_simplex_qp(x1, X0):
    """Independent solve of min ||x1 - X0'w||^2 on the simplex with SLSQP."""
    J = X0.shape[0]
    res = minimize(lambda w: np.sum((x1 - X0.T @ w) ** 2), np.full(J, 1 / J),
                   jac=lambda w: -2 * X0 @ (x1 - X0.T @ w), method="SLSQP",
                   bounds=[(0, None)] * J, constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1}],
                   options={"ftol": 1e-14, "maxiter": 1000})
    return res.x


class ScmWeights(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(0)
        self.X0 = rng.normal(size=(15, 30)).cumsum(axis=1)
        self.x1 = 0.5 * self.X0[2] + 0.3 * self.X0[7] + 0.2 * self.X0[11] + rng.normal(0, 0.3, 30)

    def test_on_simplex(self):
        w = ascm.scm_weights(self.x1, self.X0)
        self.assertTrue(np.all(w >= 0))
        self.assertAlmostEqual(w.sum(), 1.0, places=12)

    def test_matches_independent_qp(self):
        w = ascm.scm_weights(self.x1, self.X0)
        ref = reference_simplex_qp(self.x1, self.X0)
        obj = lambda v: np.sum((self.x1 - self.X0.T @ v) ** 2)
        self.assertLessEqual(obj(w), obj(ref) * (1 + 1e-6) + 1e-9)
        np.testing.assert_allclose(w, ref, atol=2e-3)

    def test_exact_donor_gets_all_weight(self):
        w = ascm.scm_weights(self.X0[4].copy(), self.X0)
        self.assertAlmostEqual(w[4], 1.0, places=6)


class RidgeAugmentation(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(1)
        self.J, self.T0, self.T = 25, 40, 50
        self.Y0 = rng.normal(size=(self.J, self.T)).cumsum(axis=1)
        self.y1 = self.Y0[:5].mean(axis=0) * 1.3 + 2 + rng.normal(0, 0.2, self.T)  # outside the convex hull

    def test_weights_form_equals_outcome_model_form(self):
        """w_aug'Y equals SCM + ridge outcome-model bias correction fitted across donors (BFR 2021 eq. 7)."""
        lam = 5.0
        fit = ascm.fit(self.y1, self.Y0, self.T0, lam=lam, fixed_effects=False)
        X0, x1 = self.Y0[:, : self.T0], self.y1[: self.T0]
        w = ascm.scm_weights(x1, X0)
        # ridge regression of each post-period outcome on pre-period outcomes, with intercept, across donors
        Xc = X0 - X0.mean(axis=0)
        Yp = self.Y0[:, self.T0:]
        eta = np.linalg.solve(Xc.T @ Xc + lam * np.eye(self.T0), Xc.T @ (Yp - Yp.mean(axis=0)))
        m = lambda x: Yp.mean(axis=0) + (x - X0.mean(axis=0)) @ eta
        expected = w @ Yp + (m(x1) - w @ np.array([m(X0[j]) for j in range(self.J)]))
        np.testing.assert_allclose(fit.counterfactual[self.T0:], expected, rtol=1e-8, atol=1e-8)

    def test_augmented_weights_sum_to_one(self):
        fit = ascm.fit(self.y1, self.Y0, self.T0, lam=1.0)
        self.assertAlmostEqual(fit.weights.sum(), 1.0, places=8)

    def test_huge_lambda_reduces_to_scm(self):
        fit = ascm.fit(self.y1, self.Y0, self.T0, lam=1e14)
        np.testing.assert_allclose(fit.weights, fit.scm_weights, atol=1e-6)

    def test_augmentation_improves_pre_fit_outside_hull(self):
        scm = ascm.fit(self.y1, self.Y0, self.T0, augment=False, fixed_effects=False)
        aug = ascm.fit(self.y1, self.Y0, self.T0, lam=1.0, fixed_effects=False)
        self.assertLess(aug.fit_nrmse(self.y1), scm.fit_nrmse(self.y1))

    def test_fixed_effects_absorb_level_differences(self):
        shifted = self.Y0[3] + 100.0
        fit = ascm.fit(shifted, self.Y0, self.T0, augment=False, fixed_effects=True)
        np.testing.assert_allclose(fit.counterfactual, shifted, atol=1e-6)

    def test_lambda_selection_returns_grid_value(self):
        lam, info = ascm.select_lambda(self.y1, self.Y0, self.T0)
        self.assertIn(lam, info["grid"])
        self.assertGreater(info["folds"], 0)


if __name__ == "__main__":
    unittest.main()
