"""The documented Python one-liner reproduces FOSIT's RFC 8785 plan hash (PREREGISTRATION.md).

The same fixture is hashed by the TypeScript implementation in web/tests/plan.test.ts,
so the two languages are checked against each other.
"""
import hashlib
import json
import os
import subprocess
import sys
import unittest

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "plan_example.fosit-plan.json")
ONE_LINER = ("import json,hashlib,sys; c=json.load(open(sys.argv[1]))['commitment']; "
             "print(hashlib.sha256(json.dumps(c,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest())")


class PlanHash(unittest.TestCase):
    def test_documented_one_liner(self):
        with open(FIXTURE, encoding="utf-8") as f:
            expected = json.load(f)["hash"]["value"]
        out = subprocess.run([sys.executable, "-c", ONE_LINER, FIXTURE], capture_output=True, text=True, check=True)
        self.assertEqual(out.stdout.strip(), expected)

    def test_any_change_changes_the_hash(self):
        with open(FIXTURE, encoding="utf-8") as f:
            c = json.load(f)["commitment"]
        h = lambda x: hashlib.sha256(json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        before = h(c)
        c["cells"][0]["geo_ids"].append("99999")
        self.assertNotEqual(before, h(c))


if __name__ == "__main__":
    unittest.main()
