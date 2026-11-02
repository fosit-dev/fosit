"""Worker API smoke test: JSON in, JSON out."""
import json
import unittest

from tests import _util  # noqa: F401
from fosit import api, synthetic


class Api(unittest.TestCase):
    def test_plan_flow_is_json_serialisable(self):
        df, _ = synthetic.make_panel(n_geos=90, n_days=140, seed=4)
        loaded = api.load_history(df.to_csv(index=False))
        self.assertTrue(loaded["ok"])
        events = []
        out = api.find_designs({"durations": [28], "n_candidates": 200, "power_designs": 2,
                                "budgets": [25000, 25000], "seed": 3,
                                "population": synthetic.population_for(df)}, events.append)
        json.dumps(out, allow_nan=False)
        self.assertTrue(events)
        self.assertIn("funnel", out)
        if out["designs"]:
            self.assertIsNotNone(out["designs"][0]["power"])

    def test_bad_file_reports_issues(self):
        out = api.load_history("date,geo_id\n2026-01-01,A\n")
        self.assertFalse(out["ok"])
        self.assertEqual(out["issues"][0]["severity"], "error")

    def test_shipped_cbsa_attributes(self):
        rows = api.geo_attributes("cbsa")
        self.assertGreater(len(rows), 900)
        self.assertTrue(any(r["geo_id"] == "35620" for r in rows))


if __name__ == "__main__":
    unittest.main()


class ApiHelpers(unittest.TestCase):
    def test_sample_history_loads_as_cbsa(self):
        text = api.sample_history("2026-10-31")
        out = api.load_history(text, "cbsa")
        self.assertTrue(out["ok"], out["issues"])
        self.assertEqual(out["summary"]["last_date"], "2026-10-31")
        self.assertIn("New York-Newark-Jersey City", [g["name"].split(",")[0] for g in out["geos"][:5]])
        chart = api.design_chart([[g["geo_id"] for g in out["geos"][40:50]]],
                                 [g["geo_id"] for g in out["geos"][50:]])
        self.assertEqual(len(chart["cells"][0]["twin"]), len(chart["dates"]))

    def test_order_export_aggregates_to_cbsa(self):
        text = ("order_date,shipping_zip,revenue,order_id\n"
                "2026-01-01T10:00:00,10001,50,a\n2026-01-01,2134,20,b\n2026-01-01,02134-1234,30,c\n"
                "2026-01-01,02134,30,c\n2026-01-02,90210,10,d\n2026-01-02,00000,5,e\n"
                + "".join(f"2026-01-03,60601,1,x{i}\n" for i in range(10)))
        out = api.aggregate_orders(text, "cbsa")
        self.assertTrue(out["ok"], out["issues"])
        codes = {i["code"] for i in out["issues"]}
        self.assertTrue({"zip_padded", "duplicate_order_id", "unmapped_zip"} <= codes)
        self.assertIn("2026-01-01,14460,2,50\n", out["csv"])
        self.assertIn("2026-01-01,35620,1,50\n", out["csv"])

    def test_user_mapping(self):
        out = api.aggregate_orders("order_date,shipping_zip\n2026-01-01,10001\n", "custom",
                                   "zip,geo_id\n10001,NYC\n")
        self.assertIn("2026-01-01,NYC,1", out["csv"])
