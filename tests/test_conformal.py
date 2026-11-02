"""Conformal inference internals (METHODOLOGY.md §5, §7.2)."""
import unittest

import numpy as np

from tests import _util  # noqa: F401
from fosit import conformal as C


class WindowSums(unittest.TestCase):
    def test_matches_brute_force(self):
        rng = np.random.default_rng(0)
        u = rng.normal(size=23)
        n_post = 6
        T = len(u)
        brute = [sum(u[(t + j) % T] for t in range(T - n_post, T)) for j in range(T)]
        np.testing.assert_allclose(C.shifted_window_sums(u, n_post), brute)

    def test_p_value_bounds_and_extremes(self):
        u = np.zeros(40)
        u[-5:] = 10.0  # the window is the most extreme block possible
        self.assertAlmostEqual(C.p_value_from_residuals(u, 5), 1 / 40)
        self.assertEqual(C.p_value_from_residuals(np.zeros(40), 5), 1.0)  # ties count as extreme

    def test_one_sided_statistics(self):
        u = np.zeros(40)
        u[-5:] = -10.0
        self.assertAlmostEqual(C.p_value_from_residuals(u, 5, "negative_sum"), 1 / 40)
        self.assertEqual(C.p_value_from_residuals(u, 5, "positive_sum"), 1.0)

    def test_iid_permutations_are_seeded_and_include_observed(self):
        u = np.random.default_rng(1).normal(size=60)
        perms = C.Permutations("iid", n=500, seed=7)
        a, b = perms.window_sums(u, 10), perms.window_sums(u, 10)
        np.testing.assert_array_equal(a, b)
        self.assertEqual(len(a), 501)
        self.assertAlmostEqual(a[0], u[-10:].sum())
        p = C.p_value_from_residuals(u, 10, perms=perms)
        self.assertGreaterEqual(p, 1 / 501)


class IntervalsAndJoint(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(3)
        T, J = 90, 30
        f = rng.normal(0, 1, T).cumsum()
        self.Y0 = 50 + np.outer(rng.normal(1, 0.3, J), f) + rng.normal(0, 1, (J, T))
        self.y1 = self.Y0[:6].mean(axis=0) + rng.normal(0, 1, T)
        self.y1[-20:] += 3.0
        self.n_post = 20

    def test_interval_contains_estimate_and_is_nested(self):
        from fosit import ascm
        lam, _ = ascm.select_lambda(self.y1, self.Y0, 70)
        pre = ascm.fit(self.y1, self.Y0, 70, lam=lam)
        att = float((self.y1 - pre.counterfactual)[70:].mean())
        ivs, evaluated = C.invert_test(self.y1, self.Y0, self.n_post, lam, att, 0.3)
        lo90, hi90 = ivs[0.90].low, ivs[0.90].high
        lo95, hi95 = ivs[0.95].low, ivs[0.95].high
        self.assertLessEqual(lo90, att)
        self.assertGreaterEqual(hi90, att)
        self.assertLessEqual(lo95, lo90 + 1e-9)
        self.assertGreaterEqual(hi95, hi90 - 1e-9)
        self.assertGreater(lo90, 0)  # a +3/day effect over 20 days is clearly detectable here
        self.assertTrue(all(p <= 1 for _, p in evaluated))
        self.assertGreater(C.p_value(self.y1, self.Y0, self.n_post, lo90, lam), 0.10)

    def test_joint_region_marginal_consistency(self):
        from fosit import ascm
        lam, _ = ascm.select_lambda(self.y1, self.Y0, 70)
        ga = C.cell_grid(self.y1, self.Y0, self.n_post, lam, -2, 8, n=21)
        gb = C.cell_grid(self.y1, self.Y0, self.n_post, lam, -2, 8, n=21)
        p = C.joint_p_values(ga, gb)
        self.assertEqual(p.shape, (21, 21))
        self.assertTrue(np.all((p > 0) & (p <= 1)))
        np.testing.assert_allclose(p, p.T)  # identical cells -> symmetric
        region = p > 0.10
        lo, hi = C.project(region, ga.taus, gb.taus, lambda a, b: a - b)
        self.assertLessEqual(lo, 0)
        self.assertGreaterEqual(hi, 0)

    def test_project_empty_region(self):
        lo, hi = C.project(np.zeros((3, 3), bool), np.arange(3.0), np.arange(3.0), lambda a, b: a - b)
        self.assertTrue(np.isnan(lo) and np.isnan(hi))


if __name__ == "__main__":
    unittest.main()
