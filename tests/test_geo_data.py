"""Integrity tests for the shipped geography tables in core/fosit/geo_data/.

Run: .venv/bin/python -m unittest tests.test_geo_data -v
"""

import csv
import hashlib
import json
import unittest
from pathlib import Path

GEO_DIR = Path(__file__).resolve().parents[1] / "core" / "fosit" / "geo_data"

STATES_51 = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID", "IL",
    "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE",
    "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD",
    "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
}


def _read(name):
    with open(GEO_DIR / name, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


class GeoDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.zcta = _read("zcta_to_geo.csv")
        cls.cbsa = _read("cbsa_attributes.csv")
        cls.states = _read("state_attributes.csv")
        cls.sources = json.loads((GEO_DIR / "SOURCES.json").read_text(encoding="utf-8"))
        cls.zmap = {r["zcta5"]: r for r in cls.zcta}
        cls.cbsa_by_id = {r["geo_id"]: r for r in cls.cbsa}

    # ---- shape -------------------------------------------------------------------
    def test_headers(self):
        self.assertEqual(list(self.zcta[0].keys()),
                         ["zcta5", "county_fips", "state", "cbsa_code", "geo_id", "land_share"])
        attr_cols = ["geo_id", "geo_name", "state", "population", "treatment_eligible", "kind"]
        self.assertEqual(list(self.cbsa[0].keys()), attr_cols)
        self.assertEqual(list(self.states[0].keys()), attr_cols)

    def test_zcta_count(self):
        self.assertGreater(len(self.zcta), 33000)
        self.assertLess(len(self.zcta), 34500)

    def test_zcta_unique_and_sorted(self):
        ids = [r["zcta5"] for r in self.zcta]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids, sorted(ids))
        for z in ids:
            self.assertRegex(z, r"^\d{5}$")

    def test_zcta_fields(self):
        for r in self.zcta:
            self.assertIn(r["state"], STATES_51)
            self.assertRegex(r["county_fips"], r"^\d{5}$")
            share = float(r["land_share"])
            self.assertGreater(share, 0.0, r)
            self.assertLessEqual(share, 1.0, r)
            if r["cbsa_code"]:
                self.assertEqual(r["geo_id"], r["cbsa_code"])
            else:
                self.assertEqual(r["geo_id"], f"{r['state']}-NONCBSA")

    def test_no_puerto_rico_or_territories(self):
        for r in self.zcta:
            self.assertNotIn(r["county_fips"][:2], {"60", "66", "69", "72", "78"})
            self.assertFalse(r["zcta5"].startswith(("006", "007", "009")), r)

    def test_ct_uses_planning_regions(self):
        ct = [r for r in self.zcta if r["state"] == "CT"]
        self.assertGreater(len(ct), 250)
        for r in ct:
            self.assertRegex(r["county_fips"], r"^091[1-9]0$")

    # ---- referential integrity ---------------------------------------------------
    def test_every_geo_id_has_attributes(self):
        missing = {r["geo_id"] for r in self.zcta} - set(self.cbsa_by_id)
        self.assertEqual(missing, set())

    def test_cbsa_attributes(self):
        ids = [r["geo_id"] for r in self.cbsa]
        self.assertEqual(len(ids), len(set(ids)))
        for r in self.cbsa:
            self.assertIn(r["state"], STATES_51)
            self.assertGreater(int(r["population"]), 0)
            self.assertTrue(r["geo_name"])
            if r["kind"] == "noncbsa":
                self.assertEqual(r["geo_id"], f"{r['state']}-NONCBSA")
                self.assertEqual(r["treatment_eligible"], "false")
            else:
                self.assertIn(r["kind"], {"metro", "micro"})
                self.assertRegex(r["geo_id"], r"^\d{5}$")
                self.assertEqual(r["treatment_eligible"], "true")
        kinds = [r["kind"] for r in self.cbsa]
        self.assertGreater(kinds.count("metro"), 380)
        self.assertGreater(kinds.count("micro"), 500)

    def test_state_attributes(self):
        self.assertEqual({r["geo_id"] for r in self.states}, STATES_51)
        for r in self.states:
            self.assertEqual(r["geo_id"], r["state"])
            self.assertEqual(r["treatment_eligible"], "true")
            self.assertEqual(r["kind"], "state")

    # ---- populations -------------------------------------------------------------
    def test_population_totals(self):
        cbsa_total = sum(int(r["population"]) for r in self.cbsa)
        state_total = sum(int(r["population"]) for r in self.states)
        national = self.sources["checks"]["national_population"]
        self.assertAlmostEqual(cbsa_total / state_total, 1.0, delta=0.001)
        self.assertAlmostEqual(cbsa_total / national, 1.0, delta=0.001)
        self.assertAlmostEqual(state_total / national, 1.0, delta=0.001)
        self.assertTrue(320_000_000 < national < 360_000_000, national)

    # ---- spot checks -------------------------------------------------------------
    def test_spot_checks(self):
        expected = {
            "10001": "35620",  # New York-Newark-Jersey City
            "90210": "31080",  # Los Angeles-Long Beach-Anaheim
            "60601": "16980",  # Chicago-Naperville-Elgin
            "06103": "25540",  # Hartford (CT planning-region trap)
            "02134": "14460",  # Boston-Cambridge-Newton
        }
        for z, geo in expected.items():
            with self.subTest(zcta=z):
                self.assertEqual(self.zmap[z]["geo_id"], geo)

    def test_rural_zcta_is_noncbsa(self):
        # 59311 (Alzada, Carter County, MT) lies outside any CBSA.
        r = self.zmap["59311"]
        self.assertEqual(r["state"], "MT")
        self.assertEqual(r["cbsa_code"], "")
        self.assertEqual(r["geo_id"], "MT-NONCBSA")
        self.assertEqual(self.cbsa_by_id["MT-NONCBSA"]["treatment_eligible"], "false")

    def test_multistate_cbsa_population_counts_all_states(self):
        # NY metro spans NY, NJ and PA (~20M); its NY counties alone hold ~13.7M, so a
        # value above 19M shows the counties of every state were aggregated.
        self.assertEqual(self.cbsa_by_id["35620"]["state"], "NY")
        self.assertGreater(int(self.cbsa_by_id["35620"]["population"]), 19_000_000)
        self.assertEqual(self.cbsa_by_id["47900"]["state"], "DC")

    # ---- provenance --------------------------------------------------------------
    def test_sources_manifest(self):
        self.assertGreaterEqual(len(self.sources["sources"]), 4)
        for s in self.sources["sources"]:
            for key in ("url", "vintage", "retrieved", "sha256"):
                self.assertTrue(s.get(key), (s.get("id"), key))
            self.assertRegex(s["url"], r"^https://www2?\.census\.gov/")
            self.assertRegex(s["sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(s["retrieved"], r"^\d{4}-\d{2}-\d{2}$")

    def test_output_hashes_match_manifest(self):
        for name, info in self.sources["outputs"].items():
            with self.subTest(file=name):
                digest = hashlib.sha256((GEO_DIR / name).read_bytes()).hexdigest()
                self.assertEqual(digest, info["sha256"])

    def test_total_size(self):
        size = sum(p.stat().st_size for p in GEO_DIR.iterdir() if p.is_file())
        self.assertLess(size, 3 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
