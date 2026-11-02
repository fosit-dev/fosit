"""End to end on the shipped examples (examples/generate_examples.py): FOSIT recovers a known effect,
and returns no lift where there is none. These are the acceptance tests for the Read module."""
import json
import os
import unittest

from tests import _util  # noqa: F401
from fosit import api

EXAMPLES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples")


def read(name):
    folder = os.path.join(EXAMPLES, name)
    plan = json.load(open(os.path.join(folder, "plan.fosit-plan.json")))
    truth = json.load(open(os.path.join(folder, "truth.json")))["cells"]
    assert api.load_history(open(os.path.join(folder, "kpi_history.csv")).read(), "cbsa")["ok"]
    assert api.load_spend(open(os.path.join(folder, "spend_delivery.csv")).read(), plan["commitment"])["ok"]
    return plan, truth, api.run_read(plan["commitment"], plan["hash"]["value"], "2026-11-02", plan.get("appendix"))


class TwoVendor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan, cls.truth, cls.r = read("two_vendor")

    def test_runs_without_warnings(self):
        self.assertTrue(self.r["ok"])
        self.assertFalse(self.r["interim"])
        self.assertEqual([c["status"] for c in self.r["checks"]], ["pass"] * len(self.r["checks"]))

    def test_truth_inside_90_percent_intervals(self):
        for cell in self.r["cells"]:
            t = self.truth[cell["id"]]
            for kpi, true in (("orders", t["true_incremental_orders"]), ("revenue", t["true_incremental_revenue"])):
                lo, hi = cell["kpis"][kpi]["intervals"]["0.9"]["incremental"]
                self.assertLessEqual(lo, true, f"{cell['label']} {kpi}")
                self.assertGreaterEqual(hi, true, f"{cell['label']} {kpi}")
            lo, hi = cell["kpis"]["orders"]["intervals"]["0.9"]["icpa"]
            self.assertLessEqual(lo, t["true_icpa"])
            self.assertTrue(hi is None or hi >= t["true_icpa"])

    def test_detects_the_effect_above_its_mde(self):
        a = next(c for c in self.r["cells"] if c["id"] == "cell_1")
        self.assertEqual(a["verdict"], "positive")

    def test_head_to_head_is_cautious(self):
        h = next(h for h in self.r["head_to_head"] if h["kpi"] == "orders")
        m = h["metrics"]["delta_incremental_per_1000"]
        true = 1000 * (self.truth["cell_1"]["true_incremental_orders"] / 50000 - self.truth["cell_2"]["true_incremental_orders"] / 50000)
        lo, hi = m["intervals"]["0.9"]
        self.assertLessEqual(lo, true)
        self.assertGreaterEqual(hi, true)

    def test_results_csv(self):
        csv = self.r["csv"]
        self.assertTrue(csv.startswith("plan_hash,scope,cell_id"))
        self.assertIn(self.plan["hash"]["value"], csv)
        self.assertIn("head_to_head", csv)


class NullEffect(unittest.TestCase):
    def test_no_cell_is_called_positive(self):
        _, truth, r = read("null_effect")
        for cell in r["cells"]:
            self.assertIn(cell["verdict"], ("no_detectable_lift", "inconclusive"), cell["label"])
            lo, hi = cell["kpis"]["orders"]["intervals"]["0.9"]["incremental"]
            self.assertLessEqual(lo, 0)
            self.assertGreaterEqual(hi, 0)
        for h in r["head_to_head"]:
            for m in h["metrics"].values():
                self.assertNotEqual(m["distinguishable"], True)


class Checks(unittest.TestCase):
    def test_interim_and_tampered_spend_are_flagged(self):
        plan, _, _ = read("two_vendor")
        folder = os.path.join(EXAMPLES, "two_vendor")
        import pandas as pd
        df = pd.read_csv(os.path.join(folder, "spend_delivery.csv"), dtype={"geo_id": str})
        # move two thirds of Vendor A's delivery into one control market
        control = plan["commitment"]["control"]["geo_ids"][0]
        a = df["cell"] == "Vendor A"
        df.loc[a & (df.index % 3 != 0), "geo_id"] = control
        leaked = df.groupby(["date", "cell", "geo_id"], as_index=False)[["impressions", "spend"]].sum().to_csv(index=False)
        self.assertTrue(api.load_spend(leaked, plan["commitment"])["ok"])
        r = api.run_read(plan["commitment"], plan["hash"]["value"], "2026-09-20")
        status = {c["id"]: c["status"] for c in r["checks"]}
        self.assertEqual(status["leakage"], "warn")
        self.assertEqual(status["timing"], "warn")
        self.assertTrue(r["interim"])

    def test_spend_file_rejects_unknown_cells(self):
        plan = json.load(open(os.path.join(EXAMPLES, "two_vendor", "plan.fosit-plan.json")))
        out = api.load_spend("date,cell,geo_id,impressions,spend\n2026-09-07,Vendor Z,35620,10,1\n", plan["commitment"])
        self.assertFalse(out["ok"])
        self.assertEqual(out["issues"][0]["code"], "spend_unknown_cell")


if __name__ == "__main__":
    unittest.main()
