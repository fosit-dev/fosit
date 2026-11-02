# Changelog

All notable changes to FOSIT are documented here. Changes to methodology, defaults, or validation tolerances are always listed, because they can change results.

## [Unreleased]

### Added: national holdout (METHODOLOGY §13)
- A new design for one campaign that runs nationally: it runs everywhere except a planner-chosen holdout (default 10%–20% of sales, at least 10 markets). Plan: new template, a required question about whether the campaign ran before the test (only "off everywhere" or "on everywhere" can be measured), holdout-share settings, design cards, lock step, email and plan PDF. Read: holdout wording, chart and report. A second in-app example, `examples/national_holdout` (US states).
- Method: the twin is built **for the holdout, from the markets with ads**, on series indexed to their own history. The gap is the share of sales the ads drove, applied to the markets with ads; iCPA uses actual spend. Building the twin the other way round (campaign markets from ~10 holdout markets) was tried and rejected: on 64 synthetic state panels it called a false positive 16% of the time, vs 5% for the method shipped.
- Plan schema: optional `commitment.design` (`type`: `geo_cells` | `national_holdout`, plus `ads_before_test`). Plans without it read as geo cells, so existing plans and their fingerprints are unchanged.
- Validation: `validation/holdout_study.py` (200 synthetic state panels) and `tests/test_holdout.py`. Results: close to unbiased (−0.6%), the planned MDE is detected 86% of the time (80% planned), but with no effect the 90% intervals hold zero only 83% of the time.

### Found: state-level designs are over-confident
- On synthetic state-level data, nominal 90% intervals cover the truth about 82–85% of the time, for the existing two-cell design as well as the national holdout (CBSA data: 92%). Documented in METHODOLOGY §13.6 and §14 (known limitations); not yet fixed.

### Added: Read module
- Core: `spend.py` (spend & delivery validation, leakage by destination) and `read.py`: per-cell estimates for every KPI with 90/95% intervals; incremental orders and revenue, lift, iCPA, iROAS and orders per 1,000 with intervals; verdicts (§8); joint-region head-to-head (§7.2); data-based honesty checks (§11); results CSV.
- Web: Read screens (load plan + fingerprint anchor + diff against the original; data files; six honesty checks; "other changes" question before results; per-cell results with charts; head-to-head; under the hood), CFO-ready PDF report with INTERIM label and "NOT THE PRE-REGISTERED ANALYSIS" watermark, results CSV, analysis config for re-running.
- `examples/`: two-vendor and null-effect datasets with a known truth (`generate_examples.py`), used by the in-app example and by `tests/test_end_to_end.py`.
- Browser tests: Read on the example, a tampered plan being caught, and Read on a phone in dark mode.

### Validation
- **Correction:** METHODOLOGY §5.1 wrongly said FOSIT's test statistic matched GeoLift's "Total". GeoLift uses the sum of |daily residuals|; FOSIT uses |sum of residuals| (the average effect). Both are documented now, `sum_abs` is available as an option, and the GeoLift comparison is done with the statistics matched.
- **GeoLift validation passes** (CI run 6). With the same λ and statistic, point estimates agree to within 1e-5, p-values are identical in all 6 cases, and CI bounds agree within 0.2–1.4% of width. With each tool's defaults, FOSIT detected all 3 real effects (GeoLift: 0) and gave one false positive in 2 nulls (GeoLift: 0). Details: METHODOLOGY §12.

### CI
- GeoLift validation: authenticated R installs from GitHub, R 4.5 (required by `bsts`, a GeoLift dependency), and augsynth pinned to 65c5a6f (2026-03-11), the version GeoLift was built against. Newer augsynth crashes inside GeoLift's `summary()` call. Runners pinned to Ubuntu 24.04; actions updated to current majors.

### Changed
- The plan now locks `decision.planned_mde_lift`, so "no detectable lift" can't be redefined after the results are in (§8).

### Added: Plan module (web)
- `/web`: React + TypeScript + Vite app; Python core runs in Pyodide 314 (Python 3.14) in a Web Worker. Pyodide and the numpy/scipy/pandas wheels are self-hosted (SHA-256 checked at build time); the core ships as a reproducible zip whose hash goes into every plan.
- Screens: "Why this exists" (flyer story), then a 7-step Plan wizard (template → test → sales data → markets → timing → find markets → lock & share), ⓘ explanations with "Read more" / "See the code" links, light/dark themes, mobile layout.
- Sales data: CSV upload, order-export helper (ZIP → CBSA/state via the shipped crosswalk, or a user mapping), clearly-labelled synthetic sample data on real metro areas.
- Locked plan: RFC 8785 + SHA-256 in the browser (Web Crypto), JSON and PDF (jsPDF) downloads, optional coin flip, email text. TypeScript and the documented Python one-liner are tested against the same fixture.
- Privacy: Content-Security-Policy `connect-src 'self'`; Playwright test runs the full flow on canary data and fails on any off-origin, non-GET or data-carrying request.
- `docs/REVIEW.md` placeholder; CI job for the web app.

### Changed
- Power simulation picks the history length per test length, keeping 6 weeks spare so there are up to 7 placebo windows (METHODOLOGY §10.1). Previously one length was shared, so adding an 8-week option made the 4-week estimate worse.
- The calibration flag is now a one-sided binomial test (3+ false hits in 7 windows at α = 0.10). The old "above 1.5α" rule flagged almost every design when there were only 5 windows.
- Sample data volume set to about 1 order per 100k people per day (~3,000 orders/day nationally).

### Added: statistical core
- `/core` Python package (`fosit`), numpy/scipy/pandas only (the Pyodide set):
  - `panel.py`: KPI-history validation (SCHEMA.md §1) and the geo × day panel.
  - `ascm.py`: ridge-augmented synthetic control with fixed effects; λ by time-series CV with the 1-SE rule.
  - `conformal.py`: conformal p-values, test-inversion intervals, joint head-to-head regions; moving-block (default) and iid permutations.
  - `estimate.py`: per-cell estimates and incremental totals.
  - `selection.py`: seeded stratified market search with share, balance and holdout-fit gates.
  - `power.py`: placebo-window power simulation, MDE, detectable iCPA/iROAS, power by budget.
  - `api.py`: JSON entry points for the web worker.
  - `synthetic.py`: factor-model panels with known effects for tests and examples.
- `core/fosit/geo_data/`: Census ZCTA→CBSA crosswalk (33,642 ZCTAs), CBSA/state attributes with Vintage 2025 populations, builder script and SOURCES.json.
- `/validation`: deterministic cases, GeoLift R harness (pinned commits), FOSIT-vs-GeoLift comparison with METHODOLOGY §12 tolerances; GitHub Actions workflows for unit tests (nightly 500-panel coverage) and validation.
- `schema/validate.py` CLI.
- 58 unit tests, including a coverage simulation.

### Methodology
- **Permutation scheme:** moving-block is confirmed as the default, with evidence added as METHODOLOGY §5.5 (500 panels: 92.2% coverage of 90% intervals and 8.0% false positives, vs 87.4% and 12.8% for iid). iid is available as a plan option. The locked-plan schema now has `method.permutations`.
- Recommended pre-period raised to "up to 26 weeks when available" (§5.5, power).
- SCM weights are solved by NNLS with a sum-to-one penalty row; the tiny ridge term ζ is dropped (§4.2).
- Market selection screens fit with plain SCM, then re-scores the best 60 with full ASCM (§9.3). Geos holding more than half the max cell share can't be treatment.
- Designs failing the power simulation's false-positive calibration check are ranked last (§9.4).

### Fixed
- p-values exactly equal to α are rejected (1 − 0.90 is 0.0999…98 in floating point).

## Draft docs (2026-11-02)
- Draft `docs/METHODOLOGY.md`, `docs/SCHEMA.md`, `docs/PREREGISTRATION.md`, `docs/UX_FLOW.md`.
- Draft `/schema` specs: KPI history, order export, spend & delivery, geo mapping, geo attributes, results (Frictionless Table Schema), and the locked plan (JSON Schema 2020-12).
- Provisional GeoLift validation tolerances (METHODOLOGY §12).
