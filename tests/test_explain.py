"""Plain answers, interactive pages, and the realistic data rules (METHODOLOGY.md §11.1, docs/UX_FLOW.md §Writing)."""
import json
import os
import re
import unittest

from tests import _util  # noqa: F401
from fosit import api, explain

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples")


def example(name):
    with open(os.path.join(ROOT, name, "plan.fosit-plan.json")) as f:
        plan = json.load(f)
    with open(os.path.join(ROOT, name, "kpi_history.csv")) as f:
        sales = f.read()
    with open(os.path.join(ROOT, name, "spend_delivery.csv")) as f:
        spend = f.read()
    return plan, sales, spend


def read(plan, sales, spend=None, today="2026-11-09", keep=lambda d: True):
    text = "\n".join(l for l in sales.splitlines() if l.startswith("date") or keep(l[:10]))
    assert api.load_history(text, plan["commitment"]["geo"]["unit"])["ok"]
    if spend:
        assert api.load_spend(spend, plan["commitment"])["ok"]
    else:
        api.clear_spend()
    return api.run_read(plan["commitment"], plan["hash"]["value"], today, plan.get("appendix"))


def sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


class LateData(unittest.TestCase):
    """Don't send people back for data because a day or two hasn't arrived yet."""

    @classmethod
    def setUpClass(cls):
        cls.plan, cls.sales, _ = example("national_holdout")     # cooldown ends 2026-10-11, ads end 2026-10-04

    def test_two_missing_cooldown_days_still_read_as_final(self):
        r = read(self.plan, self.sales, keep=lambda d: d <= "2026-10-09")
        self.assertTrue(r["ok"])
        self.assertFalse(r["interim"])
        timing = next(c for c in r["checks"] if c["id"] == "timing")
        self.assertEqual(timing["status"], "pass")
        self.assertIn("2 days before the planned end", timing["detail"])
        self.assertNotIn("notes", [k for k, v in r["summary"].items() if v])

    def test_three_missing_days_are_an_early_read(self):
        r = read(self.plan, self.sales, keep=lambda d: d <= "2026-10-08")
        self.assertTrue(r["interim"])
        self.assertTrue(r["summary"]["notes"])

    def test_the_grace_never_covers_days_with_ads(self):
        plan = json.loads(json.dumps(self.plan))
        plan["commitment"]["dates"]["cooldown_end"] = plan["commitment"]["dates"]["test_end"]   # no cooldown
        r = read(plan, self.sales, keep=lambda d: d <= "2026-10-03")
        self.assertTrue(r["interim"])

    def test_history_that_starts_late_is_used_when_8_weeks_remain(self):
        r = read(self.plan, self.sales, keep=lambda d: d >= "2026-03-20")
        self.assertTrue(r["ok"])
        self.assertEqual(r["window"]["pre_start"], "2026-03-20")
        hist = next(c for c in r["checks"] if c["id"] == "history")
        self.assertEqual(hist["status"], "warn")
        self.assertIn("you do not need more data", hist["detail"])

    def test_less_than_8_weeks_of_history_says_exactly_what_to_add(self):
        r = read(self.plan, self.sales, keep=lambda d: d >= "2026-07-15")
        self.assertFalse(r["ok"])
        self.assertIn("2026-07-13", r["errors"][0])      # 56 days before the history ends on 2026-09-06


class CrossoverLateData(unittest.TestCase):
    def test_a_last_block_missing_two_days_still_counts(self):
        plan, sales, _ = example("crossover_small")      # the last block ends 2026-10-25
        r = read(plan, sales, keep=lambda d: d <= "2026-10-23")
        self.assertTrue(r["ok"])
        self.assertFalse(r["interim"])
        self.assertEqual(len(r["cells"][0]["kpis"]["orders"]["under_the_hood"]["blocks"]), 8)
        r = read(plan, sales, keep=lambda d: d <= "2026-10-22")
        self.assertTrue(r["interim"])
        self.assertEqual(len(r["cells"][0]["kpis"]["orders"]["under_the_hood"]["blocks"]), 7)


class Answers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = {}
        for name in ("national_holdout", "crossover_small"):
            plan, sales, spend = example(name)
            cls.out[name] = (plan, read(plan, sales, spend))

    def test_the_answer_comes_first_in_plain_words(self):
        plan, r = self.out["national_holdout"]
        a = r["summary"]["cells"][0]
        self.assertEqual(a["verdict"], "positive")
        self.assertTrue(a["headline"].startswith("CTV campaign caused about"))
        self.assertIn("One extra order cost about", a["detail"])
        self.assertTrue(a["action"])

    def test_sentences_stay_short(self):
        """ASD-STE100: at most 25 words in a descriptive sentence (20 in an instruction)."""
        for plan, r in self.out.values():
            for a in r["summary"]["cells"]:
                for part in (a["headline"], a["detail"], a["action"]):
                    for s in sentences(part):
                        self.assertLessEqual(len(s.split()), 25, s)
            for group in explain.checklist(plan["commitment"]):
                for item in group["items"]:
                    self.assertLessEqual(len(item.split()), 20, item)

    def test_a_target_turns_the_answer_into_a_decision(self):
        plan, r = self.out["national_holdout"]
        c = json.loads(json.dumps(plan["commitment"]))
        c["decision"]["target_icpa"] = 60.0          # the whole cost range ($13-$51) is below it
        self.assertTrue(explain.summary(r, c)["cells"][0]["action"].startswith("Keep CTV campaign."))
        c["decision"]["target_icpa"] = 10.0
        self.assertIn("costs more than your target", explain.summary(r, c)["cells"][0]["action"])


class FadeAssumption(unittest.TestCase):
    """Every crossover result says what it assumes about how fast the ads' effect fades (METHODOLOGY §14.3, §14.5)."""

    @classmethod
    def setUpClass(cls):
        cls.plan, sales, spend = example("crossover_small")
        cls.r = read(cls.plan, sales, spend)

    def test_results_state_the_assumption_in_short_sentences(self):
        notes = " ".join(self.r["summary"]["notes"])
        self.assertIn("fades by half within about 3 days", notes)
        self.assertIn("about 20% too low", notes)
        for s in sentences(notes):
            self.assertLessEqual(len(s.split()), 25, s)

    def test_pages_and_plans_carry_it(self):
        self.assertIn('"fade_half_life":3.0', api.results_html(self.plan, self.r))
        page = api.plan_html(self.plan)
        self.assertIn("fades by half within about 3 days", page)
        self.assertIn("Fade assumption", page)

    def test_a_rule_out_asks_how_long_the_effect_lasts(self):
        r = json.loads(json.dumps(self.r))
        r["cells"][0]["verdict"] = "no_detectable_lift"
        action = explain.summary(r, self.plan["commitment"])["cells"][0]["action"]
        self.assertIn("find out how long its effect lasts", action)

    def test_older_plans_and_other_designs(self):
        self.assertEqual(explain.fade_days({"design": {"type": "crossover", "block_days": 28}}), 7.0)
        self.assertIsNone(explain.fade_days({"design": {"type": "national_holdout"}}))
        self.assertIsNone(explain.fade_note({}))


class Pages(unittest.TestCase):
    def test_every_example_makes_a_plan_page(self):
        for name in ("two_vendor", "national_holdout", "vendor_split", "crossover_small"):
            plan, _, _ = example(name)
            page = api.plan_html(plan, None, "https://example.com/#read", "brief")
            self.assertIn('"kind":"plan"', page)
            self.assertIn(plan["hash"]["value"], page)
            self.assertIn('"level":"brief"', page)
            self.assertNotRegex(page, r"<script[^>]+src=|<link[^>]+href=[\"']?http")   # self-contained, offline

    def test_labels_cannot_break_out_of_the_page(self):
        plan, _, _ = example("crossover_small")
        plan = json.loads(json.dumps(plan))
        plan["commitment"]["test_name"] = "</script><script>alert(1)</script>"
        page = api.plan_html(plan)
        self.assertEqual(page.count("</script>"), 1)
        self.assertIn("&lt;/script&gt;", page.split("</title>")[0])

    def test_results_page_carries_the_answer_and_every_check(self):
        plan, sales, spend = example("crossover_small")
        r = read(plan, sales, spend)
        checks = [{"status": "pass", "title": "Plan match", "detail": "Exactly the plan."}] + r["checks"]
        page = api.results_html(plan, r, None, checks, "full", True)
        self.assertIn('"kind":"results"', page)
        self.assertIn("CTV campaign caused about", page)
        self.assertIn('"title":"Plan match"', page)


if __name__ == "__main__":
    unittest.main()
