#!/usr/bin/env python3
"""Build FOSIT's shipped geography tables from public-domain US Census files.

Outputs (written to core/fosit/geo_data/ by default):
  zcta_to_geo.csv        one row per 2020 ZCTA in the 50 states + DC
  cbsa_attributes.csv    one row per CBSA in scope + one "{ST}-NONCBSA" row per state
  state_attributes.csv   one row per state (50 + DC)
  SOURCES.json           URL, vintage, retrieval date and SHA-256 of every source,
                         plus row counts and SHA-256 of every output

Standard library only. The .xlsx delineation file is read with zipfile + xml.etree.

Usage (see core/fosit/geo_data/README.md for the download commands):
  python core/tools/build_geo_data.py --src /path/to/geo_src --retrieved 2026-11-02

Individual source paths can be given instead of (or to override) --src:
  --zcta-county, --ct-cousub-zcta, --delineation, --popest
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import hashlib
import io
import json
import posixpath
import re
import sys
import zipfile
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "core" / "fosit" / "geo_data"

# --------------------------------------------------------------------------------------
# Source registry. URLs verified against www2.census.gov on 2026-11-02.
# --------------------------------------------------------------------------------------
SOURCES = {
    "zcta_county": {
        "file": "tab20_zcta520_county20_natl.txt",
        "url": "https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/"
               "tab20_zcta520_county20_natl.txt",
        "vintage": "2020 Census tabulation geography (2020 ZCTA5 to 2020 county relationship file)",
        "description": "Pipe-delimited ZCTA-to-county relationship file with land and water "
                       "area of every ZCTA-county part. National.",
    },
    "ct_cousub_zcta": {
        "file": "acs22_cousub22_zcta520_st09.txt",
        "url": "https://www2.census.gov/geo/docs/maps-data/data/rel2022/"
               "acs22_cousub22_zcta520_st09.txt",
        "vintage": "2022 ACS geography (2022 Connecticut county subdivisions to 2020 ZCTA5)",
        "description": "Pipe-delimited Connecticut county-subdivision-to-ZCTA relationship file. "
                       "2022 county subdivision GEOIDs embed the planning-region county code "
                       "(09110-09190), so it re-assigns CT ZCTA parts from the 8 legacy "
                       "counties to the 9 planning regions.",
    },
    "delineation": {
        "file": "list1_2023.xlsx",
        "url": "https://www2.census.gov/programs-surveys/metro-micro/geographies/"
               "reference-files/2023/delineation-files/list1_2023.xlsx",
        "vintage": "July 2023 (OMB Bulletin No. 23-01)",
        "publisher": "U.S. Office of Management and Budget; file published by the U.S. Census Bureau",
        "description": "CBSAs, Metropolitan Divisions and CSAs with their component counties.",
    },
    "popest": {
        "file": "co-est2025-alldata.csv",
        "url": "https://www2.census.gov/programs-surveys/popest/datasets/2020-2025/"
               "counties/totals/co-est2025-alldata.csv",
        "vintage": "Vintage 2025 county population estimates (column POPESTIMATE2025, July 1 2025)",
        "description": "Annual resident population estimates for states (SUMLEV 040) and "
                       "counties (SUMLEV 050).",
    },
}

# 50 states + DC. Puerto Rico (72) and the Island Areas (60, 66, 69, 78) are out of scope.
STATES = {
    "01": ("AL", "Alabama"), "02": ("AK", "Alaska"), "04": ("AZ", "Arizona"),
    "05": ("AR", "Arkansas"), "06": ("CA", "California"), "08": ("CO", "Colorado"),
    "09": ("CT", "Connecticut"), "10": ("DE", "Delaware"), "11": ("DC", "District of Columbia"),
    "12": ("FL", "Florida"), "13": ("GA", "Georgia"), "15": ("HI", "Hawaii"),
    "16": ("ID", "Idaho"), "17": ("IL", "Illinois"), "18": ("IN", "Indiana"),
    "19": ("IA", "Iowa"), "20": ("KS", "Kansas"), "21": ("KY", "Kentucky"),
    "22": ("LA", "Louisiana"), "23": ("ME", "Maine"), "24": ("MD", "Maryland"),
    "25": ("MA", "Massachusetts"), "26": ("MI", "Michigan"), "27": ("MN", "Minnesota"),
    "28": ("MS", "Mississippi"), "29": ("MO", "Missouri"), "30": ("MT", "Montana"),
    "31": ("NE", "Nebraska"), "32": ("NV", "Nevada"), "33": ("NH", "New Hampshire"),
    "34": ("NJ", "New Jersey"), "35": ("NM", "New Mexico"), "36": ("NY", "New York"),
    "37": ("NC", "North Carolina"), "38": ("ND", "North Dakota"), "39": ("OH", "Ohio"),
    "40": ("OK", "Oklahoma"), "41": ("OR", "Oregon"), "42": ("PA", "Pennsylvania"),
    "44": ("RI", "Rhode Island"), "45": ("SC", "South Carolina"), "46": ("SD", "South Dakota"),
    "47": ("TN", "Tennessee"), "48": ("TX", "Texas"), "49": ("UT", "Utah"),
    "50": ("VT", "Vermont"), "51": ("VA", "Virginia"), "53": ("WA", "Washington"),
    "54": ("WV", "West Virginia"), "55": ("WI", "Wisconsin"), "56": ("WY", "Wyoming"),
}
USPS_TO_FIPS = {usps: fips for fips, (usps, _name) in STATES.items()}

CT_FIPS = "09"


class BuildError(RuntimeError):
    pass


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_pipe_table(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="|"))


def _col_index(cell_ref: str) -> int:
    letters = re.match(r"[A-Z]+", cell_ref).group(0)
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch) - 64)
    return idx - 1


def read_xlsx_first_sheet(path: Path) -> list[list[str]]:
    """Return the first worksheet of an .xlsx as a list of rows (strings), stdlib only."""
    ns = {
        "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
    }
    with zipfile.ZipFile(path) as zf:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", ns):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{ns['m']}}}t")))
        wb = ET.fromstring(zf.read("xl/workbook.xml"))
        first = wb.find("m:sheets/m:sheet", ns)
        rid = first.get(f"{{{ns['r']}}}id")
        rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        target = next(r.get("Target") for r in rels.findall("pr:Relationship", ns)
                      if r.get("Id") == rid)
        sheet_path = target.lstrip("/") if target.startswith("/") else posixpath.normpath(
            posixpath.join("xl", target))
        sheet = ET.fromstring(zf.read(sheet_path))

    rows: list[list[str]] = []
    for row in sheet.iter(f"{{{ns['m']}}}row"):
        values: dict[int, str] = {}
        for c in row.findall("m:c", ns):
            t = c.get("t")
            if t == "inlineStr":
                val = "".join(x.text or "" for x in c.iter(f"{{{ns['m']}}}t"))
            else:
                v = c.find("m:v", ns)
                if v is None or v.text is None:
                    continue
                val = shared[int(v.text)] if t == "s" else v.text
            values[_col_index(c.get("r"))] = val
        if values:
            width = max(values) + 1
            rows.append([values.get(i, "") for i in range(width)])
        else:
            rows.append([])
    return rows


def _fmt_share(x: float) -> str:
    return f"{x:.4f}"


# --------------------------------------------------------------------------------------
# Loaders
# --------------------------------------------------------------------------------------
def load_popest(path: Path):
    """Return (pop_column, {county_fips: (name, pop)}, {state_fips: pop})."""
    with open(path, encoding="latin-1", newline="") as fh:
        reader = csv.DictReader(fh)
        pop_cols = sorted(c for c in reader.fieldnames if re.fullmatch(r"POPESTIMATE\d{4}", c))
        if not pop_cols:
            raise BuildError("no POPESTIMATEyyyy column in population file")
        pop_col = pop_cols[-1]
        counties: dict[str, tuple[str, int]] = {}
        states: dict[str, int] = {}
        for r in reader:
            st = r["STATE"].zfill(2)
            if st not in STATES:
                continue
            if r["SUMLEV"] == "040":
                states[st] = int(r[pop_col])
            elif r["SUMLEV"] == "050":
                counties[st + r["COUNTY"].zfill(3)] = (r["CTYNAME"], int(r[pop_col]))
    missing = set(STATES) - set(states)
    if missing:
        raise BuildError(f"population file lacks states {sorted(missing)}")
    return pop_col, counties, states


def load_delineation(path: Path):
    """Return {cbsa_code: {title, kind}} and {county_fips: cbsa_code} for in-scope counties."""
    rows = read_xlsx_first_sheet(path)
    header_idx = next(i for i, r in enumerate(rows) if r and r[0].strip() == "CBSA Code")
    header = [h.strip() for h in rows[header_idx]]
    col = {name: header.index(name) for name in (
        "CBSA Code", "CBSA Title", "Metropolitan/Micropolitan Statistical Area",
        "FIPS State Code", "FIPS County Code")}
    cbsas: dict[str, dict] = {}
    county_to_cbsa: dict[str, str] = {}
    dropped_out_of_scope: set[str] = set()
    for r in rows[header_idx + 1:]:
        r = r + [""] * (len(header) - len(r))
        code = r[col["CBSA Code"]].strip()
        if not re.fullmatch(r"\d{5}", code):
            continue  # footnotes / blank rows
        st = r[col["FIPS State Code"]].strip().split(".")[0].zfill(2)
        cty = r[col["FIPS County Code"]].strip().split(".")[0].zfill(3)
        if st not in STATES:
            dropped_out_of_scope.add(code)
            continue
        area_type = r[col["Metropolitan/Micropolitan Statistical Area"]].strip()
        if area_type.startswith("Metropolitan"):
            kind = "metro"
        elif area_type.startswith("Micropolitan"):
            kind = "micro"
        else:
            raise BuildError(f"unknown CBSA type {area_type!r} for {code}")
        title = r[col["CBSA Title"]].strip()
        prev = cbsas.setdefault(code, {"title": title, "kind": kind})
        if prev["title"] != title or prev["kind"] != kind:
            raise BuildError(f"inconsistent title/type for CBSA {code}")
        fips = st + cty
        if county_to_cbsa.get(fips, code) != code:
            raise BuildError(f"county {fips} listed in two CBSAs")
        county_to_cbsa[fips] = code
    dropped_out_of_scope -= set(cbsas)
    return cbsas, county_to_cbsa, sorted(dropped_out_of_scope)


def load_zcta_parts(zcta_county_path: Path, ct_path: Path):
    """Return ({zcta: (land, water)}, {zcta: {county_fips: [land, water]}}, ct_report).

    Connecticut parts from the 2020 file (legacy counties 09001-09015) are replaced by
    parts from the 2022 county-subdivision file, aggregated to planning region (09110-09190).
    """
    totals: dict[str, tuple[int, int]] = {}
    parts: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    legacy_ct_land: dict[str, int] = defaultdict(int)
    for r in read_pipe_table(zcta_county_path):
        z = r["GEOID_ZCTA5_20"].strip()
        cty = r["GEOID_COUNTY_20"].strip()
        if not z or not cty:
            continue
        totals[z] = (int(r["AREALAND_ZCTA5_20"]), int(r["AREAWATER_ZCTA5_20"]))
        land, water = int(r["AREALAND_PART"]), int(r["AREAWATER_PART"])
        if cty.startswith(CT_FIPS):
            legacy_ct_land[z] += land
            continue
        p = parts[z][cty]
        p[0] += land
        p[1] += water

    new_ct_land: dict[str, int] = defaultdict(int)
    for r in read_pipe_table(ct_path):
        z = r["GEOID_ZCTA5_20"].strip()
        cousub = r["GEOID_COUSUB_22"].strip()
        if not z or not cousub:
            continue
        region = cousub[:5]
        if not re.fullmatch(r"091[1-9]0", region):
            raise BuildError(f"unexpected CT county code in cousub {cousub}")
        if z not in totals:
            raise BuildError(f"CT file references ZCTA {z} absent from the 2020 ZCTA-county file")
        land, water = int(r["AREALAND_PART"]), int(r["AREAWATER_PART"])
        p = parts[z][region]
        p[0] += land
        p[1] += water
        new_ct_land[z] += land

    missing = sorted(set(legacy_ct_land) - set(new_ct_land))
    if missing:
        raise BuildError(f"CT ZCTAs with no planning-region parts: {missing[:10]}")
    max_rel_diff = 0.0
    for z, old in legacy_ct_land.items():
        if old:
            max_rel_diff = max(max_rel_diff, abs(new_ct_land[z] - old) / old)
    report = {
        "ct_zctas_reassigned": len(legacy_ct_land),
        "ct_max_relative_land_difference_2020_vs_2022": round(max_rel_diff, 6),
    }
    # 2022 vs 2020 boundary/shoreline updates move a few CT ZCTAs by ~1% of land area.
    if max_rel_diff > 0.05:
        raise BuildError(f"CT land totals differ by up to {max_rel_diff:.2%} between sources")
    return totals, parts, report


# --------------------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------------------
def write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    path.write_text(buf.getvalue(), encoding="utf-8")


def build(paths: dict[str, Path], out_dir: Path, retrieved: str) -> dict:
    pop_col, county_pop, state_pop = load_popest(paths["popest"])
    cbsas, county_to_cbsa, dropped_cbsas = load_delineation(paths["delineation"])
    totals, parts, ct_report = load_zcta_parts(paths["zcta_county"], paths["ct_cousub_zcta"])

    # Consistency: every delineation county must have a population estimate.
    no_pop = sorted(set(county_to_cbsa) - set(county_pop))
    if no_pop:
        raise BuildError(f"delineation counties missing from population file: {no_pop}")

    # ---- ZCTA assignment ----
    zrows = []
    dropped_zctas = 0
    for z in sorted(parts):
        cands = parts[z]
        # Largest land area wins; ties -> larger water area -> lowest county FIPS.
        cty, (land, water) = min(cands.items(), key=lambda kv: (-kv[1][0], -kv[1][1], kv[0]))
        st_fips = cty[:2]
        if st_fips not in STATES:
            dropped_zctas += 1
            continue
        if cty not in county_pop:
            raise BuildError(f"ZCTA {z} assigned to county {cty} with no population estimate")
        # Denominator is the sum of the ZCTA's parts. Outside CT this equals the published
        # ZCTA land area; in CT it absorbs the small 2020-vs-2022 boundary differences so
        # that shares never exceed 1.
        tot_land = sum(v[0] for v in cands.values())
        tot_water = sum(v[1] for v in cands.values())
        share = land / tot_land if tot_land else (water / tot_water if tot_water else 1.0)
        usps = STATES[st_fips][0]
        cbsa = county_to_cbsa.get(cty, "")
        geo_id = cbsa if cbsa else f"{usps}-NONCBSA"
        zrows.append([z, cty, usps, cbsa, geo_id, _fmt_share(share)])

    # ---- CBSA + NONCBSA attributes ----
    cbsa_pop: dict[str, int] = defaultdict(int)
    noncbsa_pop: dict[str, int] = defaultdict(int)
    for fips, (_name, pop) in county_pop.items():
        code = county_to_cbsa.get(fips)
        if code:
            cbsa_pop[code] += pop
        else:
            noncbsa_pop[fips[:2]] += pop

    crow = []
    for code in sorted(cbsas):
        info = cbsas[code]
        title = info["title"]
        first_state = title.rsplit(", ", 1)[-1].split("-")[0].strip()
        if first_state not in USPS_TO_FIPS:
            raise BuildError(f"cannot parse state from CBSA title {title!r}")
        member_states = {f[:2] for f, c in county_to_cbsa.items() if c == code}
        if USPS_TO_FIPS[first_state] not in member_states:
            raise BuildError(f"title state {first_state} not among counties of {code}")
        crow.append([code, title, first_state, cbsa_pop[code], "true", info["kind"]])
    for st_fips in sorted(noncbsa_pop, key=lambda f: STATES[f][0]):
        usps, name = STATES[st_fips]
        crow.append([f"{usps}-NONCBSA", f"Rest of {name} (outside metro/micro areas)", usps,
                     noncbsa_pop[st_fips], "false", "noncbsa"])

    # Every geo_id used by a ZCTA must exist.
    known = {r[0] for r in crow}
    unknown = sorted({r[4] for r in zrows} - known)
    if unknown:
        raise BuildError(f"ZCTA geo_ids missing from cbsa_attributes: {unknown[:10]}")

    # ---- State attributes ----
    srow = []
    for st_fips, (usps, name) in sorted(STATES.items(), key=lambda kv: kv[1][0]):
        county_sum = sum(p for f, (_n, p) in county_pop.items() if f[:2] == st_fips)
        if county_sum != state_pop[st_fips]:
            raise BuildError(f"{usps}: county sum {county_sum} != state total {state_pop[st_fips]}")
        srow.append([usps, name, usps, state_pop[st_fips], "true", "state"])

    national = sum(state_pop.values())
    if sum(r[3] for r in crow) != national:
        raise BuildError("CBSA + NONCBSA populations do not sum to the national total")

    # ---- Write ----
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "zcta_to_geo.csv": (["zcta5", "county_fips", "state", "cbsa_code", "geo_id", "land_share"],
                            zrows),
        "cbsa_attributes.csv": (["geo_id", "geo_name", "state", "population",
                                 "treatment_eligible", "kind"], crow),
        "state_attributes.csv": (["geo_id", "geo_name", "state", "population",
                                  "treatment_eligible", "kind"], srow),
    }
    for name, (header, rows) in outputs.items():
        write_csv(out_dir / name, header, rows)

    pop_year = pop_col[-4:]
    manifest = {
        "description": "Provenance of the FOSIT geography tables. All sources are works of the "
                       "U.S. Government (U.S. Census Bureau / OMB) and are in the public domain "
                       "in the United States (17 U.S.C. 105).",
        "generated_by": "core/tools/build_geo_data.py",
        "scope": "50 states + DC. Puerto Rico and the Island Areas are excluded.",
        "population_column": pop_col,
        "population_reference_date": f"{pop_year}-07-01",
        "sources": [],
        "checks": {
            **ct_report,
            "zctas_out_of_scope_dropped": dropped_zctas,
            "cbsas_out_of_scope_dropped": dropped_cbsas,
            "national_population": national,
        },
        "outputs": {},
    }
    for key, meta in SOURCES.items():
        p = paths[key]
        manifest["sources"].append({
            "id": key,
            "publisher": meta.get("publisher", "U.S. Census Bureau"),
            "url": meta["url"],
            "file": p.name,
            "vintage": meta["vintage"],
            "description": meta["description"],
            "retrieved": retrieved,
            "bytes": p.stat().st_size,
            "sha256": sha256_file(p),
        })
    for name, (_h, rows) in outputs.items():
        manifest["outputs"][name] = {"rows": len(rows), "sha256": sha256_file(out_dir / name)}
    (out_dir / "SOURCES.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, help="directory holding the downloaded source files")
    for key, meta in SOURCES.items():
        ap.add_argument(f"--{key.replace('_', '-')}", type=Path, dest=key,
                        help=f"path to {meta['file']}")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory")
    ap.add_argument("--retrieved", default=_dt.date.today().isoformat(),
                    help="date the sources were downloaded (YYYY-MM-DD); default today")
    args = ap.parse_args(argv)

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.retrieved):
        ap.error("--retrieved must be YYYY-MM-DD")
    paths: dict[str, Path] = {}
    for key, meta in SOURCES.items():
        p = getattr(args, key) or (args.src / meta["file"] if args.src else None)
        if p is None or not p.is_file():
            ap.error(f"missing source {key}: pass --src or --{key.replace('_', '-')} "
                     f"(download {meta['url']})")
        paths[key] = p

    try:
        manifest = build(paths, args.out, args.retrieved)
    except BuildError as e:
        print(f"build_geo_data: error: {e}", file=sys.stderr)
        return 1
    for name, info in manifest["outputs"].items():
        print(f"{name}: {info['rows']} rows")
    print(json.dumps(manifest["checks"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
