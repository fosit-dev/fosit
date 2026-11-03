"""National holdout (METHODOLOGY.md §13): market selection, the holdout estimator, power, and the shipped example."""
import json
import os
import unittest

import numpy as np

from tests import _util  # noqa: F401
from fosit import api, holdout, power, selection, synthetic
from fosit.panel import load_kpi_history

EXAMPLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples", "national_holdout")


def state_panel(seed=3, n_days=161, end="2026-08-30"):
    attrs = api.geo_attributes("state")
    df = synthetic.sample_state_history(attrs, end, n_days=n_days, seed=seed)
    return df, {a["geo_id"]: a["population"] for a in attrs}


class Selection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        df, pop = state_panel()
        cls.panel, _ = load_kpi_history(df.to_csv(index=False))
        cls.excluded = {"TX"}
        cls.cfg = selection.SelectionConfig(n_cells=1, holdout=True, share_min=0.10, share_max=0.20, pre_days=126,
                                            test_days=28, n_candidates=600, seed=7, excluded=cls.excluded, population=pop)
        cls.out = selection.MarketSelector(cls.panel, cls.cfg).run()

    def test_finds_designs(self):
        self.assertGreater(len(self.out["designs"]), 0)

    def test_campaign_is_everything_not_held_out_or_excluded(self):
        for d in self.out["designs"]:
            campaign, held = set(d.cells[0]), set(d.control)
            self.assertFalse(campaign & held)
            self.assertFalse((campaign | held) & self.excluded)
            self.assertEqual(campaign | held | self.excluded, set(self.panel.geos))

    def test_gates_hold(self):
        for d in self.out["designs"]:
            self.assertTrue(self.cfg.share_min <= d.control_share <= self.cfg.share_max)
            self.assertGreaterEqual(len(d.control), self.cfg.min_holdout_geos)
            self.assertLessEqual(d.balance_score, self.cfg.balance_max)
            self.assertLessEqual(max(d.fit), self.cfg.fit_max)
            # holdout vs campaign compares shape, not size (§13.2)
            self.assertNotIn("share", d.balance)
            self.assertNotIn("seasonality", d.balance)
            self.assertIn("per_capita", d.balance)

    def test_fit_is_scored_on_the_holdout(self):
        """Regression: the fit score must come from the held-out markets' twin, not from (nearly) every market."""
        sel = selection.MarketSelector(self.panel, self.cfg)
        d = self.out["designs"][0]
        rows = [self.panel.rows(d.cells[0])]
        n_fit = sel.Y.shape[1] - self.cfg.test_days
        y1, Y0 = holdout.index_rows(sel.Y, self.panel.rows(d.control), np.array(self.panel.rows(d.cells[0])), n_fit)
        from fosit import ascm
        fit = ascm.fit(y1, Y0, n_fit)
        r = y1[n_fit:] - fit.counterfactual[n_fit:]
        self.assertAlmostEqual(sel.holdout_fit(rows, augment=True)[0], float(np.sqrt(np.mean(r**2)) / y1[:n_fit].mean()), places=6)


class Split(unittest.TestCase):
    """§13.7: several vendors share every market that isn't held out; each gets its own twin of the holdout."""

    @classmethod
    def setUpClass(cls):
        # seed 3's panel has one state with 16% of sales at 3x the sales per person, so no 2-way split is fair: that's
        # the balance gate doing its job, so this test uses a panel where fair splits exist
        df, pop = state_panel(seed=2026)
        cls.panel, _ = load_kpi_history(df.to_csv(index=False))
        cls.cfg = selection.SelectionConfig(n_cells=2, holdout=True, share_min=0.15, share_max=0.25, pre_days=126,
                                            test_days=28, n_candidates=600, seed=7, population=pop)
        cls.out = selection.MarketSelector(cls.panel, cls.cfg).run()

    def test_partition(self):
        self.assertGreater(len(self.out["designs"]), 0)
        for d in self.out["designs"]:
            a, b, held = set(d.cells[0]), set(d.cells[1]), set(d.control)
            self.assertFalse(a & b or (a | b) & held)
            self.assertEqual(a | b | held, set(self.panel.geos))
            self.assertTrue(self.cfg.share_min <= d.control_share <= self.cfg.share_max)
            self.assertTrue(min(len(a), len(b), len(held)) >= self.cfg.min_holdout_geos)
            self.assertEqual(len(d.fit), 2)
            self.assertLessEqual(d.balance_score, self.cfg.balance_max)
            self.assertIn("share", d.balance)
            self.assertIn("holdout_per_capita", d.balance)

    def test_split_is_seeded(self):
        again = selection.MarketSelector(self.panel, self.cfg).run()
        self.assertEqual([d.key for d in again["designs"]], [d.key for d in self.out["designs"]])


class Translation(unittest.TestCase):
    """§13.4: from the holdout's gap to incremental sales in the campaign markets."""

    def setUp(self):
        df, _ = synthetic.make_panel(n_geos=60, n_days=140, seed=4, factor_sd=0.01, dispersion=1e6, trend_sd=0.0)
        self.df = df
        self.geos = sorted(df.geo_id.unique())
        self.held, self.campaign = self.geos[:12], self.geos[12:]

    def read(self, lift):
        df = self.df.astype({"orders": float})
        mask = df.geo_id.isin(self.campaign) & (df.date >= "2026-04-27")
        df.loc[mask, "orders"] = df.loc[mask, "orders"] * (1 + lift)
        panel, _ = load_kpi_history(df.to_csv(index=False))
        est = holdout.estimate_holdout(panel, "orders", self.held, self.campaign, np.arange(112), np.arange(112, 140), levels=(0.9,))
        true = float(df.loc[mask, "orders"].sum()) * lift / (1 + lift)
        return est, true

    def test_index_rows(self):
        mat = np.arange(1.0, 41.0).reshape(4, 10)
        y, Y = holdout.index_rows(mat, [0, 1], [2, 3], 5)
        self.assertAlmostEqual(y[:5].mean(), 1.0)
        np.testing.assert_allclose(Y[:, :5].mean(axis=1), 1.0)

    def test_recovers_a_known_lift(self):
        est, true = self.read(0.10)
        self.assertLess(est.att, 0)                  # the holdout sits below its with-ads twin
        lo, hi = est.incremental_interval(0.9)
        self.assertLess(lo, est.incremental)
        self.assertLess(est.incremental, hi)
        self.assertLessEqual(lo, true)
        self.assertGreaterEqual(hi, true)
        self.assertAlmostEqual(est.incremental / true, 1.0, delta=0.25)
        self.assertAlmostEqual(est.observed_total - est.counterfactual_total, est.incremental)

    def test_no_effect_interval_contains_zero(self):
        est, _ = self.read(0.0)
        lo, hi = est.incremental_interval(0.9)
        self.assertLessEqual(lo, 0)
        self.assertGreaterEqual(hi, 0)

    def test_ads_share_is_decreasing_in_tau(self):
        est, _ = self.read(0.05)
        self.assertGreater(est.ads_share(-0.1), est.ads_share(0.0))
        self.assertEqual(est.ads_share(0.0), 0.0)


class Power(unittest.TestCase):
    def test_lift_goes_into_the_campaign_markets(self):
        df, _ = state_panel(seed=5)
        panel, _ = load_kpi_history(df.to_csv(index=False))
        geos = sorted(panel.geos)
        held, campaign = geos[::4], [g for g in geos if g not in geos[::4]]
        cfg = power.PowerConfig(pre_days=84, durations=(28,), holdout=True, n_windows=4)
        sim = power.PowerSimulator(panel, [campaign], held, cfg)
        windows = sim._windows(campaign, 28)
        self.assertTrue(windows and all(w.weights is not None for w in windows))
        w = windows[0]
        # a big lift in the donors must be detected; no lift must leave the twin unchanged
        self.assertTrue(sim._detected(w, 0.5))
        np.testing.assert_allclose(w.pre_cf + w.weights @ (w.Y0 - w.Y0), w.pre_cf)


class Example(unittest.TestCase):
    """The shipped example (examples/generate_examples.py national_holdout): recover the truth, pass every check."""

    @classmethod
    def setUpClass(cls):
        cls.plan = json.load(open(os.path.join(EXAMPLE, "plan.fosit-plan.json")))
        cls.truth = json.load(open(os.path.join(EXAMPLE, "truth.json")))["cells"]["cell_1"]
        assert api.load_history(open(os.path.join(EXAMPLE, "kpi_history.csv")).read(), "state")["ok"]
        assert api.load_spend(open(os.path.join(EXAMPLE, "spend_delivery.csv")).read(), cls.plan["commitment"])["ok"]
        cls.r = api.run_read(cls.plan["commitment"], cls.plan["hash"]["value"], "2026-11-02", cls.plan.get("appendix"))

    def test_design_and_checks(self):
        self.assertTrue(self.r["ok"])
        self.assertEqual(self.r["design"], "national_holdout")
        self.assertEqual([c["status"] for c in self.r["checks"]], ["pass"] * len(self.r["checks"]))
        self.assertEqual(self.r["cells"][0]["kpis"]["orders"]["series"]["role"], "holdout")
        self.assertEqual(self.r["head_to_head"], [])

    def test_truth_inside_90_percent_intervals(self):
        m = self.r["cells"][0]["kpis"]
        for kpi, true in (("orders", self.truth["true_incremental_orders"]), ("revenue", self.truth["true_incremental_revenue"])):
            lo, hi = m[kpi]["intervals"]["0.9"]["incremental"]
            self.assertLessEqual(lo, true, kpi)
            self.assertGreaterEqual(hi, true, kpi)
        lo, hi = m["orders"]["intervals"]["0.9"]["icpa"]
        self.assertLessEqual(lo, self.truth["true_icpa"])
        self.assertTrue(hi is None or hi >= self.truth["true_icpa"])

    def test_detects_the_effect_above_its_mde(self):
        self.assertEqual(self.r["cells"][0]["verdict"], "positive")

    def test_missing_campaign_market_warns_instead_of_failing(self):
        c = json.loads(json.dumps(self.plan["commitment"]))
        c["cells"][0]["geo_ids"] = sorted(c["cells"][0]["geo_ids"] + ["ZZ"])
        r = api.run_read(c, "", "2026-11-02")
        self.assertTrue(r["ok"])
        self.assertIn("campaign_coverage", [x["id"] for x in r["checks"]])


class VendorSplitExample(unittest.TestCase):
    """examples/vendor_split: two vendors share the country with a holdout. Ranges must hold the truth."""

    @classmethod
    def setUpClass(cls):
        folder = os.path.join(os.path.dirname(EXAMPLE), "vendor_split")
        with open(os.path.join(folder, "plan.fosit-plan.json")) as f:
            cls.plan = json.load(f)
        with open(os.path.join(folder, "truth.json")) as f:
            cls.truth = json.load(f)["cells"]
        with open(os.path.join(folder, "kpi_history.csv")) as f:
            assert api.load_history(f.read(), "state")["ok"]
        with open(os.path.join(folder, "spend_delivery.csv")) as f:
            assert api.load_spend(f.read(), cls.plan["commitment"])["ok"]
        cls.r = api.run_read(cls.plan["commitment"], cls.plan["hash"]["value"], "2026-11-02", cls.plan.get("appendix"))

    def test_each_vendor_is_measured_against_the_holdout(self):
        self.assertTrue(self.r["ok"])
        self.assertEqual(self.r["design"], "national_holdout")
        self.assertEqual(len(self.r["cells"]), 2)
        for cell in self.r["cells"]:
            self.assertEqual(cell["kpis"]["orders"]["series"]["role"], "holdout")
            self.assertEqual(cell["kpis"]["orders"]["placebo"]["n"], 40)

    def test_truth_inside_90_percent_intervals(self):
        for cell in self.r["cells"]:
            t = self.truth[cell["id"]]
            for kpi, true in (("orders", t["true_incremental_orders"]), ("revenue", t["true_incremental_revenue"])):
                lo, hi = cell["kpis"][kpi]["intervals"]["0.9"]["incremental"]
                self.assertLessEqual(lo, true, f"{cell['label']} {kpi}")
                self.assertGreaterEqual(hi, true, f"{cell['label']} {kpi}")

    def test_head_to_head_contains_the_true_difference(self):
        h = next(h for h in self.r["head_to_head"] if h["kpi"] == "orders")
        lo, hi = h["metrics"]["delta_incremental"]["intervals"]["0.9"]
        true = self.truth["cell_1"]["true_incremental_orders"] - self.truth["cell_2"]["true_incremental_orders"]
        self.assertLessEqual(lo, true)
        self.assertGreaterEqual(hi, true)


if __name__ == "__main__":
    unittest.main()
