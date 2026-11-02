"""KPI history validation rules (SCHEMA.md §1, METHODOLOGY.md §3)."""
import unittest

from tests import _util  # noqa: F401
from fosit.panel import load_kpi_history


def codes(issues):
    return {i.code for i in issues}


class KpiHistoryValidation(unittest.TestCase):
    def test_clean_file_pivots(self):
        text = "date,geo_id,orders,revenue\n2026-01-01,A,1,10\n2026-01-01,B,2,20\n2026-01-02,A,3,30\n2026-01-02,B,4,40\n"
        panel, issues = load_kpi_history(text)
        self.assertIsNotNone(panel)
        self.assertEqual(panel.geos, ["A", "B"])
        self.assertEqual(panel.kpis["orders"].tolist(), [[1, 3], [2, 4]])
        self.assertIn("short_history", codes(issues))

    def test_headers_are_case_and_space_insensitive_and_bom_tolerant(self):
        panel, _ = load_kpi_history(chr(0xFEFF) + " Date , GEO_ID ,Orders\n2026-01-01,A,1\n")
        self.assertIsNotNone(panel)

    def test_needs_a_kpi(self):
        panel, issues = load_kpi_history("date,geo_id\n2026-01-01,A\n")
        self.assertIsNone(panel)
        self.assertIn("missing_kpi", codes(issues))

    def test_revenue_only_is_fine(self):
        panel, _ = load_kpi_history("date,geo_id,revenue\n2026-01-01,A,10\n")
        self.assertEqual(list(panel.kpis), ["revenue"])

    def test_duplicates_are_errors(self):
        panel, issues = load_kpi_history("date,geo_id,orders\n2026-01-01,A,1\n2026-01-01,A,2\n")
        self.assertIsNone(panel)
        self.assertIn("duplicate_rows", codes(issues))

    def test_bad_date_reports_spreadsheet_row(self):
        panel, issues = load_kpi_history("date,geo_id,orders\n01/02/2026,A,1\n")
        self.assertIsNone(panel)
        bad = [i for i in issues if i.code == "bad_date"][0]
        self.assertEqual(bad.examples, [2])

    def test_whole_missing_day_is_a_gap_not_zero(self):
        panel, issues = load_kpi_history("date,geo_id,orders\n2026-01-01,A,1\n2026-01-03,A,1\n")
        self.assertIsNone(panel)
        self.assertIn("date_gap", codes(issues))

    def test_missing_geo_days_are_zero_filled_and_reported(self):
        panel, issues = load_kpi_history("date,geo_id,orders\n2026-01-01,A,1\n2026-01-01,B,1\n2026-01-02,A,5\n")
        self.assertEqual(panel.kpis["orders"].tolist(), [[1, 5], [1, 0]])
        filled = [i for i in issues if i.code == "zero_filled"][0]
        self.assertEqual(filled.count, 1)

    def test_negative_orders_error_negative_revenue_warning(self):
        _, issues = load_kpi_history("date,geo_id,orders\n2026-01-01,A,-1\n")
        self.assertIn("negative_orders", codes(issues))
        panel, issues = load_kpi_history("date,geo_id,revenue\n2026-01-01,A,-5\n")
        self.assertIsNotNone(panel)
        self.assertIn("negative_revenue", codes(issues))

    def test_unknown_geos_are_excluded_with_warning(self):
        panel, issues = load_kpi_history("date,geo_id,orders\n2026-01-01,A,1\n2026-01-01,Z,1\n", valid_geos={"A"})
        self.assertEqual(panel.geos, ["A"])
        self.assertIn("unknown_geo", codes(issues))

    def test_thousands_separators_are_accepted(self):
        panel, _ = load_kpi_history('date,geo_id,revenue\n2026-01-01,A,"1,234.5"\n')
        self.assertAlmostEqual(panel.kpis["revenue"][0, 0], 1234.5)


if __name__ == "__main__":
    unittest.main()
