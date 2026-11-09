"""Judging twin fit on weekly totals for small advertisers (METHODOLOGY.md §9.3)."""
import json
import os
import unittest

import numpy as np

from tests import _util  # noqa: F401
from fosit import api, synthetic
from fosit.estimate import fit_error
from fosit.panel import load_kpi_history

EXAMPLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples", "national_holdout")


def state_sales(per_day: float, seed: int = 11):
    attrs = api.geo_attributes("state")
    per_100k = per_day / (sum(a["population"] for a in attrs) / 1e5)
    return synthetic.sample_state_history(attrs, "2026-11-01", n_days=182, seed=seed, orders_per_100k=per_100k)


class FitError(unittest.TestCase):
    def test_weekly_totals_cancel_day_to_day_noise(self):
        rng = np.random.default_rng(0)
        level = 80.0                                   # a small holdout: 80 orders a day
        resid = rng.poisson(level, 182) - level        # a perfect twin: only counting noise is left
        daily, weekly = fit_error(resid, level, 1), fit_error(resid, level, 7)
        self.assertAlmostEqual(daily, 1 / np.sqrt(level), delta=0.02)
        self.assertLess(weekly, daily / 2)

    def test_drift_still_counts_weekly(self):
        level = 100.0
        drift = np.linspace(0, 20, 28)                 # a twin drifting 20% off over four weeks
        self.assertGreater(fit_error(drift, level, 7), 0.08)

    def test_blocks_end_on_the_last_day(self):
        r = np.r_[np.full(3, 100.0), np.zeros(14)]      # a partial week at the start is dropped
        self.assertEqual(fit_error(r, 10.0, 7), 0.0)


class Planning(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.small = state_sales(400)

    def search(self, fit_period):
        assert api.load_history(self.small.to_csv(index=False), "state")["ok"]
        return api.find_designs({"design": "national_holdout", "n_cells": 2, "pre_days": 182, "durations": [28],
                                 "seed": 1, "budgets": [50000, 50000], "share_min": 0.18, "share_max": 0.22,
                                 "fit_period": fit_period, "power_designs": 0})

    def test_auto_picks_weekly_for_small_sales_and_finds_designs(self):
        daily = self.search("day")
        auto = self.search("auto")
        self.assertEqual(daily["fit_period"], "day")
        self.assertEqual(daily["funnel"]["passed_fit"], 0)       # the problem: counting noise fails every design
        self.assertEqual(auto["fit_period"], "week")
        self.assertGreater(auto["funnel"]["passed_fit"], 0)

    def test_auto_stays_daily_for_large_sales(self):
        assert api.load_history(state_sales(6500).to_csv(index=False), "state")["ok"]
        out = api.find_designs({"design": "national_holdout", "n_cells": 2, "pre_days": 182, "durations": [28],
                                "seed": 1, "budgets": [1, 1], "share_min": 0.18, "share_max": 0.22, "power_designs": 0})
        self.assertEqual(out["fit_period"], "day")


class Read(unittest.TestCase):
    def test_plan_locks_how_fit_is_judged(self):
        with open(os.path.join(EXAMPLE, "plan.fosit-plan.json")) as f:
            plan = json.load(f)
        with open(os.path.join(EXAMPLE, "kpi_history.csv")) as f:
            assert api.load_history(f.read(), "state")["ok"]
        c = plan["commitment"]
        day = api.run_read(c, "", "2026-11-02")["cells"][0]["kpis"]["orders"]
        c = json.loads(json.dumps(c))
        c["thresholds"]["pre_fit_period"] = "week"
        week = api.run_read(c, "", "2026-11-02")["cells"][0]["kpis"]["orders"]
        self.assertEqual(day["pre_fit_period"], "day")
        self.assertEqual(week["pre_fit_period"], "week")
        self.assertNotAlmostEqual(day["pre_fit_nrmse"], week["pre_fit_nrmse"])
        self.assertEqual(day["incremental"], week["incremental"])   # only the check changes, never the estimate


if __name__ == "__main__":
    unittest.main()
