# Changelog

All notable changes to FOSIT are documented here. Changes to methodology, defaults, or validation tolerances are always listed, because they can change results.

## [Unreleased]

### Added: Read module
- Core: `spend.py` (spend & delivery validation, leakage by destination) and `read.py`: per-cell estimates for every KPI with 90/95% intervals; incremental orders and revenue, lift, iCPA, iROAS and orders per 1,000 with intervals; verdicts (§8); joint-region head-to-head (§7.2); data-based honesty checks (§11); results CSV.
- Web: Read screens (load plan + fingerprint anchor + diff against the original; data files; six honesty checks; "other changes" question before results; per-cell results with charts; head-to-head; under the hood), CFO-ready PDF report with INTERIM label and "NOT THE PRE-REGISTERED ANALYSIS" watermark, results CSV, analysis config for re-running.
- `examples/`: two-vendor and null-effect datasets with a known truth (`generate_examples.py`), used by the in-app example and by `tests/test_end_to_end.py`.
- Browser tests: Read on the example, a tampered plan being caught, and Read on a phone in dark mode.

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
