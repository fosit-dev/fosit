"""Power simulation (METHODOLOGY.md §10)."""
import unittest

from tests import _util  # noqa: F401
from fosit import power as W
from fosit import synthetic
from fosit.panel import load_kpi_history


class Power(unittest.TestCase):
    def test_placebo_starts(self):
        self.assertEqual(W.placebo_starts(200, 84, 35, 10, 7), [165, 158, 151, 144, 137, 130, 123, 116, 109, 102])
        self.assertEqual(W.placebo_starts(120, 84, 35, 10, 7), [85])
        self.assertEqual(W.placebo_starts(100, 84, 35, 10, 7), [])

    def test_curve_shape_and_money(self):
        df, _ = synthetic.make_panel(n_geos=80, n_days=168, seed=9)
        panel, _ = load_kpi_history(df.to_csv(index=False))
        cell = [f"G{i:04d}" for i in range(0, 40, 4)]
        control = [g for g in panel.geos if g not in cell]
        sim = W.PowerSimulator(panel, [cell], control, W.PowerConfig(durations=(28,), n_windows=6))
        curve = sim.run()[0]["curves"][0]
        self.assertEqual(curve["windows"], 6)
        pts = {p["effect"]: p["power"] for p in curve["points"]}
        self.assertLessEqual(pts[0.0], 0.5)
        if curve["mde"] is not None:
            self.assertGreaterEqual(pts[curve["mde"]], 0.8)
            m = W.money(curve, 10000.0)
            self.assertAlmostEqual(m["detectable_icpa"], 10000.0 / (curve["mde"] * curve["baseline_test_total"]))
            self.assertGreaterEqual(W.power_at_budget(curve, 10000.0, m["detectable_icpa"] / 2), 0.8 - 1e-9)

    def test_money_without_mde(self):
        self.assertIsNone(W.money({"mde": None}, 1000)["detectable_icpa"])


if __name__ == "__main__":
    unittest.main()


class Calibration(unittest.TestCase):
    def test_flag_needs_surprising_count(self):
        # 1 of 5 windows at alpha=0.10 is normal; 3 of 7 is not.
        self.assertFalse(W.calibration_flag(1, 5, 0.10))
        self.assertFalse(W.calibration_flag(2, 7, 0.10))
        self.assertTrue(W.calibration_flag(3, 7, 0.10))
        self.assertFalse(W.calibration_flag(0, 0, 0.10))
