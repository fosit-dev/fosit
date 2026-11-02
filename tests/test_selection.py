"""Market selection invariants (METHODOLOGY.md §9)."""
import unittest

from tests import _util  # noqa: F401
from fosit import selection as S
from fosit import synthetic
from fosit.panel import load_kpi_history


class MarketSelection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        df, _ = synthetic.make_panel(n_geos=150, n_days=140, seed=5)
        cls.panel, _ = load_kpi_history(df.to_csv(index=False))
        cls.population = synthetic.population_for(df)
        cls.excluded = {"G0003", "G0050"}
        cls.not_eligible = {"G0010", "G0011"}
        cls.cfg = S.SelectionConfig(pre_days=84, test_days=21, n_candidates=400, seed=42,
                                    excluded=cls.excluded, not_eligible=cls.not_eligible,
                                    population=cls.population, screen_top=20)
        cls.out = S.MarketSelector(cls.panel, cls.cfg).run()

    def test_finds_designs(self):
        self.assertGreater(len(self.out["designs"]), 0)

    def test_cells_disjoint_from_each_other_control_and_excluded(self):
        for d in self.out["designs"]:
            a, b, ctrl = set(d.cells[0]), set(d.cells[1]), set(d.control)
            self.assertFalse(a & b)
            self.assertFalse((a | b) & ctrl)
            self.assertFalse((a | b | ctrl) & self.excluded)
            self.assertFalse((a | b) & self.not_eligible)
            self.assertEqual(a | b | ctrl | self.excluded, set(self.panel.geos))

    def test_gates_hold(self):
        for d in self.out["designs"]:
            self.assertTrue(all(self.cfg.share_min <= s <= self.cfg.share_max for s in d.shares))
            self.assertGreaterEqual(d.control_share, self.cfg.min_control_share)
            self.assertLessEqual(d.balance_score, self.cfg.balance_max)
            self.assertLessEqual(max(d.fit), self.cfg.fit_max)
            self.assertIn("population", d.balance)

    def test_same_seed_same_designs(self):
        again = S.MarketSelector(self.panel, self.cfg).run()
        self.assertEqual([d.key for d in again["designs"]], [d.key for d in self.out["designs"]])

    def test_relative_gap(self):
        self.assertAlmostEqual(S.relative_gap([10, 10]), 0.0)
        self.assertAlmostEqual(S.relative_gap([9, 11]), 0.2)
        self.assertAlmostEqual(S.relative_gap([9, 10, 11]), 0.2)


if __name__ == "__main__":
    unittest.main()
