# Contributing

Thanks for helping make incrementality measurement more honest.

## Ground rules

1. **Vendor-neutral.** No vendor names in code, defaults, examples or copy. Cells are labelled by users.
2. **Client-side only.** No feature may send user data anywhere. The privacy test must keep passing.
3. **Methodology first.** A change that can change a result (estimator, inference, defaults, thresholds, tolerances) starts as an edit to `docs/METHODOLOGY.md`, with evidence, and is recorded in `docs/CHANGELOG.md`.
4. **No copied code from GeoLift or augsynth.** They are reference implementations for validation only (see METHODOLOGY §12).
5. **New dependencies need discussion first.** The core uses only what ships with Pyodide (numpy, scipy, pandas).

## Running the checks

```bash
python -m unittest discover -s tests -t .        # core, incl. coverage simulation (FOSIT_COVERAGE_SIMS=500 for the full run)
cd web && pnpm install && pnpm prepare-runtime && pnpm test && pnpm test:e2e
```

The GeoLift comparison runs in CI (`.github/workflows/validation.yml`); see `validation/README.md` to run it locally.

## Style

Python: readable over clever, a docstring naming the METHODOLOGY section a function implements. TypeScript: small components, plain-English copy, an ⓘ explanation for every statistic.
