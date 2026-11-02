# Independent review

**Status: no independent review has been completed yet.** This page is linked from the app's footer and will list every review, good or bad, with the reviewer's name, affiliation, date, scope and the exact commit they reviewed.

## How to review FOSIT

1. Read [METHODOLOGY.md](METHODOLOGY.md). Every number the app shows links to a section of it.
2. Run the tests: `python -m unittest discover -s tests -t .` (Python core, including the coverage simulation) and `pnpm test && pnpm test:e2e` in `/web`.
3. Run the GeoLift comparison in [`/validation`](../validation/README.md).
4. Check the privacy claim yourself: open the app with your browser's network panel and run a plan. Only same-origin static files should load, and nothing should be sent.

Open an issue with your findings. We'll link it here whether or not we agree.
