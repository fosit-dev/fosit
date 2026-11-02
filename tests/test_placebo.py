"""Placebo calibration (METHODOLOGY.md §5.6): ranges are checked against placebo cells and never get narrower."""
import json
import math
import os
import unittest

import numpy as np

from tests import _util  # noqa: F401
from fosit import api, placebo, power
from fosit.estimate import cell_series, estimate
from fosit.panel import load_kpi_history
from fosit import synthetic

EXAMPLES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples")


class Quantile(unittest.TestCase):
    def test_conformal_index(self):
        z = np.arange(1, 20)                          # 19 placebos: 90% -> the 18th smallest |z|
        self.assertEqual(placebo.quantile(z, 0.9), 18)
        self.assertEqual(placebo.quantile(-z, 0.9), 18)

    def test_too_few_placebos_is_unbounded(self):
        self.assertTrue(math.isinf(placebo.quantile(np.arange(1, 5), 0.9)))


class Calibrate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        df, _ = synthetic.make_panel(n_geos=60, n_days=140, seed=8)
        cls.panel, _ = load_kpi_history(df.to_csv(index=False))
        geos = sorted(cls.panel.geos)
        cls.cell, cls.control = geos[:8], geos[8:]
        cls.pre, cls.post = np.arange(112), np.arange(112, 140)

    def fresh(self):
        s = cell_series(self.panel, "orders", self.cell, self.control, self.pre, self.post)
        return estimate(s, levels=(0.9, 0.95), kpi="orders")

    def test_never_narrower_and_p_value_never_lower(self):
        base = self.fresh()
        for z in (np.zeros(40), np.full(40, 50.0), np.linspace(-3, 3, 40)):
            est = self.fresh()
            cal = placebo.calibrate(est, z, (0.9, 0.95))
            for lv in (0.9, 0.95):
                self.assertLessEqual(est.intervals[lv][0], base.intervals[lv][0])
                self.assertGreaterEqual(est.intervals[lv][1], base.intervals[lv][1])
            self.assertGreaterEqual(est.p_value, base.p_value)
            self.assertEqual(cal.n, 40)

    def test_large_placebo_errors_widen(self):
        est = self.fresh()
        cal = placebo.calibrate(est, np.full(40, 50.0), (0.9,))
        self.assertTrue(cal.widened[0.9])
        self.assertAlmostEqual(cal.p_value, 41 / 41)

    def test_placebos_are_seeded_and_need_a_pool(self):
        a = placebo.placebo_errors(self.panel, "orders", 8, self.control, self.pre, self.post, n=12, seed=[3, 0, 0])
        b = placebo.placebo_errors(self.panel, "orders", 8, self.control, self.pre, self.post, n=12, seed=[3, 0, 0])
        np.testing.assert_array_equal(a, b)
        self.assertEqual(len(a), 12)
        self.assertEqual(len(placebo.placebo_errors(self.panel, "orders", 2, self.control[:4], self.pre, self.post)), 0)


class ReadAndPower(unittest.TestCase):
    def test_read_locks_it_in_the_plan(self):
        folder = os.path.join(EXAMPLES, "two_vendor")
        plan = json.load(open(os.path.join(folder, "plan.fosit-plan.json")))
        assert api.load_history(open(os.path.join(folder, "kpi_history.csv")).read(), "cbsa")["ok"]
        c = json.loads(json.dumps(plan["commitment"]))
        c["method"].pop("placebo_calibration", None)
        plain = api.run_read(c, "", "2026-11-02")
        c["method"]["placebo_calibration"] = {"n": 40}
        cal = api.run_read(c, "", "2026-11-02")
        for a, b in zip(plain["cells"], cal["cells"]):
            self.assertIsNone(a["kpis"]["orders"]["placebo"])
            self.assertEqual(b["kpis"]["orders"]["placebo"]["n"], 40)
            lo0, hi0 = a["kpis"]["orders"]["intervals"]["0.9"]["incremental"]
            lo1, hi1 = b["kpis"]["orders"]["intervals"]["0.9"]["incremental"]
            self.assertLessEqual(lo1, lo0 + 1e-6)
            self.assertGreaterEqual(hi1, hi0 - 1e-6)

    def test_power_requires_the_placebo_range_too(self):
        df, _ = synthetic.make_panel(n_geos=60, n_days=168, seed=9)
        panel, _ = load_kpi_history(df.to_csv(index=False))
        geos = sorted(panel.geos)
        cell, control = geos[:8], geos[8:]
        off = power.PowerSimulator(panel, [cell], control, power.PowerConfig(pre_days=84, durations=(28,), n_windows=5))
        on = power.PowerSimulator(panel, [cell], control, power.PowerConfig(pre_days=84, durations=(28,), n_windows=5, placebos=20))
        q = on._placebo_q(cell, 28)
        self.assertGreater(q, 0)
        windows = off._windows(cell, 28)
        for effect in (0.05, 0.1, 0.2):
            self.assertLessEqual(on._power(windows, effect, q), off._power(windows, effect))


if __name__ == "__main__":
    unittest.main()
