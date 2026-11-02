"""End-to-end recovery and calibration on synthetic panels (METHODOLOGY.md §12).

Coverage: FOSIT_COVERAGE_SIMS controls the number of simulated panels
(default 200 for CI speed; the methodology target of 500 runs nightly).
"""
import os
import unittest

import numpy as np

from tests import _util  # noqa: F401
from fosit import conformal as C
from fosit import estimate as E
from fosit import synthetic
from fosit.panel import load_kpi_history

N_DAYS, N_PRE, TEST_DAYS, COOLDOWN = 119, 84, 28, 7


def one_cell(seed, lift, n_geos=100, n_cell=10):
    rng = np.random.default_rng(seed)
    geos = [f"G{i:04d}" for i in range(n_geos)]
    cell = sorted(rng.choice(geos, n_cell, replace=False).tolist())
    df, truth = synthetic.make_panel(n_geos=n_geos, n_days=N_DAYS, seed=seed,
                                     lifts={"cell": (cell, N_PRE, N_PRE + TEST_DAYS - 1, lift)})
    panel, _ = load_kpi_history(df.to_csv(index=False))
    donors = [g for g in geos if g not in cell]
    series = E.cell_series(panel, "orders", cell, donors, np.arange(N_PRE), np.arange(N_PRE, N_DAYS))
    return series, truth.incremental_orders["cell"]


class Recovery(unittest.TestCase):
    def test_recovers_injected_lift(self):
        series, true_inc = one_cell(seed=11, lift=0.20)
        for perms in (C.Permutations("moving_block"), C.Permutations("iid")):
            est = E.estimate(series, kpi="orders", perms=perms)
            lo, hi = est.incremental_interval(0.90)
            self.assertAlmostEqual(est.incremental / true_inc, 1.0, delta=0.15)
            self.assertLessEqual(lo, true_inc)
            self.assertGreaterEqual(hi, true_inc)
        # iid permutations detect this lift; block permutations are too weak here (see METHODOLOGY.md §5.5)
        self.assertLess(est.p_value, 0.10)
        self.assertGreater(lo, 0)

    def test_null_is_not_called_positive(self):
        series, _ = one_cell(seed=12, lift=0.0)
        est = E.estimate(series, kpi="orders")
        lo, hi = est.incremental_interval(0.90)
        self.assertLessEqual(lo, 0)
        self.assertGreaterEqual(hi, 0)


class Coverage(unittest.TestCase):
    def test_block_permutations(self):
        self._coverage(C.Permutations("moving_block"))

    def test_iid_permutations_diagnostic(self):
        """iid permutations are NOT calibrated when residuals are autocorrelated (METHODOLOGY.md §5.5).

        This test documents the size of the problem rather than requiring calibration:
        it fails only if iid coverage collapses far below what we have published.
        """
        self._coverage(C.Permutations("iid", n=1000, seed=5), strict=False)

    def _coverage(self, perms, strict=True):
        n = int(os.environ.get("FOSIT_COVERAGE_SIMS", "200"))
        covered90 = covered95 = false_pos = 0
        for k in range(n):
            lift = 0.10 if k % 2 else 0.0
            series, true_inc = one_cell(seed=1000 + k, lift=lift)
            est = E.estimate(series, kpi="orders", perms=perms)
            lo90, hi90 = est.incremental_interval(0.90)
            lo95, hi95 = est.incremental_interval(0.95)
            covered90 += lo90 <= true_inc <= hi90
            covered95 += lo95 <= true_inc <= hi95
            if lift == 0.0:
                false_pos += est.p_value <= 0.10
        rate90, rate95, fpr = covered90 / n, covered95 / n, false_pos / (n // 2)
        print(f"\n[{perms.kind}] coverage90={rate90:.3f} coverage95={rate95:.3f} false_positive_rate={fpr:.3f} (n={n})")
        if not strict:
            self.assertGreaterEqual(rate90, 0.75)
            return
        se = np.sqrt(0.9 * 0.1 / n)
        self.assertGreaterEqual(rate90, 0.90 - max(0.04, 2.5 * se))
        self.assertLessEqual(rate90, 0.90 + max(0.04, 2.5 * se))
        self.assertGreaterEqual(rate95, 0.95 - max(0.03, 2.5 * np.sqrt(0.95 * 0.05 / n)))
        self.assertLessEqual(fpr, 0.10 + 2.5 * np.sqrt(0.09 / (n // 2)))


if __name__ == "__main__":
    unittest.main()
