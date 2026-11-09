"""Geo crossover (METHODOLOGY.md §14): the design's arithmetic, planning, and reading the shipped example."""
import json
import math
import os
import unittest

import numpy as np
import pandas as pd

from tests import _util  # noqa: F401
from fosit import api, crossover, synthetic
from fosit.panel import load_kpi_history
from fosit.spend import SpendData

EXAMPLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples", "crossover_small")


class Arithmetic(unittest.TestCase):
    def test_schedules_are_balanced_and_complete(self):
        s = crossover.schedules(8)
        self.assertEqual(len(s), math.comb(8, 4))
        self.assertTrue((s.sum(axis=1) == 4).all())
        sched = crossover.random_schedule(8, np.random.default_rng(1))
        self.assertEqual(sched.count("A"), 4)

    def test_estimate_recovers_a_known_lift(self):
        a_on = np.array([1, 0, 0, 1, 1, 0, 1, 0], float)
        d = 0.02 * np.arange(8) - 0.05 + 0.1 * (2 * a_on - 1)      # drift between halves plus a 0.1 log lift
        self.assertAlmostEqual(crossover.estimate_tau(d, a_on), 0.1, delta=0.03)

    def test_randomization_test_is_exact(self):
        rng = np.random.default_rng(3)
        scheds = crossover.schedules(8)
        ps = []
        for _ in range(400):
            d = rng.normal(0, 0.05, 8)                              # no effect at all
            a_on = scheds[rng.integers(len(scheds))]
            ps.append(crossover.p_value(d, a_on, 0.0, scheds))
        self.assertAlmostEqual(np.mean(np.array(ps) <= 0.10), 0.10, delta=0.04)

    def test_adstock_conserves_the_effect(self):
        on = np.r_[np.ones(14), np.zeros(200)]
        self.assertAlmostEqual(crossover.adstock(on, 3.0).sum(), 14, delta=0.01)


class Planning(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        attrs = api.geo_attributes("state")
        per_100k = 100 / (sum(a["population"] for a in attrs) / 1e5)
        cls.df = synthetic.sample_state_history(attrs, "2026-11-01", n_days=182, seed=5, orders_per_100k=per_100k)
        assert api.load_history(cls.df.to_csv(index=False), "state")["ok"]
        cls.out = api.find_designs({"design": "crossover", "block_days": 14, "durations": [112], "seed": 1,
                                    "budgets": [60000], "power_designs": 2})

    def test_halves_cover_every_market_once(self):
        d = self.out["designs"][0]
        a, b = set(d["cells"][0]), set(d["control"])
        self.assertFalse(a & b)
        self.assertEqual(a | b, set(self.df.geo_id))
        self.assertLessEqual(d["balance_score"], 0.10)
        self.assertIsNotNone(d["power"]["cells"][0]["curves"][0]["mde"])

    def test_test_length_must_be_an_even_number_of_blocks(self):
        with self.assertRaises(ValueError):
            api.find_designs({"design": "crossover", "block_days": 14, "durations": [98], "budgets": [1]})


class Example(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(EXAMPLE, "plan.fosit-plan.json")) as f:
            cls.plan = json.load(f)
        with open(os.path.join(EXAMPLE, "truth.json")) as f:
            cls.truth = json.load(f)["cells"]["cell_1"]
        with open(os.path.join(EXAMPLE, "kpi_history.csv")) as f:
            cls.sales = f.read()
        with open(os.path.join(EXAMPLE, "spend_delivery.csv")) as f:
            cls.spend = f.read()
        assert api.load_history(cls.sales, "state")["ok"]
        assert api.load_spend(cls.spend, cls.plan["commitment"])["ok"]
        cls.r = api.run_read(cls.plan["commitment"], cls.plan["hash"]["value"], "2026-11-09", cls.plan.get("appendix"))

    def test_reads_as_a_crossover(self):
        self.assertTrue(self.r["ok"])
        self.assertEqual(self.r["design"], "crossover")
        self.assertEqual(self.r["head_to_head"], [])
        self.assertEqual([c["status"] for c in self.r["checks"]], ["pass"] * len(self.r["checks"]))
        self.assertEqual(self.r["cells"][0]["kpis"]["orders"]["series"]["role"], "crossover")

    def test_truth_inside_90_percent_range_and_detected(self):
        m = self.r["cells"][0]["kpis"]
        for kpi, true in (("orders", self.truth["true_incremental_orders"]), ("revenue", self.truth["true_incremental_revenue"])):
            lo, hi = m[kpi]["intervals"]["0.9"]["incremental"]
            self.assertLessEqual(lo, true, kpi)
            self.assertGreaterEqual(hi, true, kpi)
        self.assertEqual(self.r["cells"][0]["verdict"], "positive")

    def test_ads_in_the_dark_half_are_flagged(self):
        c = self.plan["commitment"]
        rows = pd.read_csv(pd.io.common.StringIO(self.spend), dtype={"geo_id": str})
        rows["date"] = pd.to_datetime(rows["date"])
        rows = rows.rename(columns={"cell": "cell_id"})
        rows["cell_id"] = "cell_1"
        dark = rows.copy()          # the same delivery, shifted into the half that should be dark
        swap = dict(zip(c["cells"][0]["geo_ids"], c["control"]["geo_ids"])) | dict(zip(c["control"]["geo_ids"], c["cells"][0]["geo_ids"]))
        dark["geo_id"] = dark["geo_id"].map(lambda g: swap.get(g, g))
        leak = crossover.leakage(SpendData(dark), set(c["cells"][0]["geo_ids"]), set(c["control"]["geo_ids"]),
                                 c["design"]["schedule"], c["dates"]["test_start"], c["design"]["block_days"])
        self.assertGreater(leak["leak_share"], 0.9)

    def test_interim_read_uses_whole_blocks(self):
        cut = (pd.Timestamp(self.plan["commitment"]["dates"]["test_start"]) + pd.Timedelta(days=47)).strftime("%Y-%m-%d")
        panel_text = "\n".join(l for l in self.sales.splitlines() if l[:10] < cut or l.startswith("date"))
        assert api.load_history(panel_text, "state")["ok"]
        r = api.run_read(self.plan["commitment"], "", cut)
        self.assertTrue(r["ok"])
        self.assertTrue(r["interim"])
        self.assertEqual(r["window"]["days"] % self.plan["commitment"]["design"]["block_days"], 0)
        assert api.load_history(self.sales, "state")["ok"]


if __name__ == "__main__":
    unittest.main()
