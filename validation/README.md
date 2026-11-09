# Validation against GeoLift

FOSIT's statistics are written from the papers (docs/METHODOLOGY.md §17). This folder checks them against
Meta's open-source [GeoLift](https://github.com/facebookincubator/GeoLift) (R), run as an **external
reference only**. No GeoLift or augsynth code is copied into FOSIT.

| File | What it does |
|---|---|
| `make_cases.py` | Writes deterministic synthetic cases (`cases/<name>/data.csv`, `case.json`): null effects, 10% and 20% lifts, a single-geo test |
| `run_geolift.R` | Runs `GeoLift::GeoLift()` with FOSIT's settings (Ridge, fixed effects, `stat_test = "Total"`, `conformal_type = "block"`, α = 0.10) and writes JSON |
| `compare.py` | Runs FOSIT on the same cases two ways: **matched** (GeoLift's λ and GeoLift's test statistic, gating) and **defaults** (each tool's own, informational, scored against the truth). Writes `out/report.md` and exits non-zero if a matched comparison is outside the METHODOLOGY.md §12 tolerances |

CI: `.github/workflows/validation.yml` pins GeoLift and augsynth to exact commits.

Run locally (needs R ≥ 4.1 with GeoLift installed):

```bash
python validation/make_cases.py validation/cases
Rscript validation/run_geolift.R validation/cases validation/out/geolift block
python validation/compare.py validation/cases validation/out/geolift validation/out/report.md
```

Note: GeoLift's own default is `conformal_type = "iid"`. FOSIT defaults to moving-block permutations because
iid permutations under-cover when daily residuals are autocorrelated (METHODOLOGY.md §5.5), so the harness
runs GeoLift with `"block"` to compare like with like.
