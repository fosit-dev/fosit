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

The GeoLift comparison covers the geo-cells estimator only. The other designs are checked by FOSIT's own simulations on synthetic data with a known truth:

| File | What it checks |
|---|---|
| `calibration_study.py` | Coverage, false positives and power of geo cells, the national holdout and the vendor split, with or without placebo calibration and the weekly fit gate (METHODOLOGY §5.6, §9.3, §13) |
| `crossover_study.py` | Halves taking turns (§14.5): honesty with no effect, power and coverage at the planned lift, and what a wrong answer to "how long do the ads keep working?" does (`--half-life` above the planning half-life) |

Run locally (needs R ≥ 4.1 with GeoLift installed):

```bash
python validation/make_cases.py validation/cases
Rscript validation/run_geolift.R validation/cases validation/out/geolift block
python validation/compare.py validation/cases validation/out/geolift validation/out/report.md
```

Note: GeoLift's own default is `conformal_type = "iid"`. FOSIT defaults to moving-block permutations because
iid permutations under-cover when daily residuals are autocorrelated (METHODOLOGY.md §5.5), so the harness
runs GeoLift with `"block"` to compare like with like.
