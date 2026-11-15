"""The status every reader sees is the same everywhere, and the crossover's planning half-life is one rule in the app, the
skill's CLI and the validation study (docs/REVIEW.md; METHODOLOGY.md §14.4)."""
import os
import re
import sys
import unittest

from tests import _util  # noqa: F401

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def text(rel: str) -> str:
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class Status(unittest.TestCase):
    def test_every_entry_point_says_pre_release_and_not_reviewed(self):
        for rel in ("README.md", "docs/METHODOLOGY.md", "docs/SCHEMA.md", "docs/PREREGISTRATION.md"):
            head = text(rel)[:4000]
            self.assertIn("pre-release", head, rel)
            self.assertIn("not yet independently reviewed", head, rel)
            self.assertNotIn("not yet implemented", text(rel), rel)
        self.assertIn("no independent review has been completed yet", text("docs/REVIEW.md").lower())
        self.assertIn("not yet independently reviewed", text("web/src/components/VersionNote.tsx"))

    def test_geolift_is_called_a_cross_check_of_geo_cells_only(self):
        self.assertNotIn("Validated against Meta's GeoLift", text("README.md"))
        self.assertIn("geo-cells estimator", text("README.md"))


class PlanningHalfLife(unittest.TestCase):
    def test_one_rule_in_the_app_the_cli_and_the_study(self):
        sys.path.insert(0, os.path.join(ROOT, "validation"))
        import crossover_study
        web = {(int(b), float(h)) for b, h in re.findall(r"blockDays: (\d+), washoutDays: \d+, halfLife: (\d+)", text("web/src/plan/state.ts"))}
        self.assertEqual(web, set(crossover_study.APP_PLANNING_HALF_LIFE.items()))
        cli = text("skill/fosit/scripts/fosit_cli.py")
        self.assertIn('block = 28 if a.lingering == "long" else 14', cli)
        self.assertIn('"half_life": 7 if a.lingering == "long" else 3', cli)


if __name__ == "__main__":
    unittest.main()
