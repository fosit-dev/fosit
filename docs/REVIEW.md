# Independent review

**Status: no independent review has been completed yet.** This page is linked from the app's footer and will list every review, good or bad, with the reviewer's name, affiliation, date, scope and the exact commit they reviewed.

## How to review FOSIT

1. Read [METHODOLOGY.md](METHODOLOGY.md). Every number the app shows links to a section of it.
2. Run the tests: `python -m unittest discover -s tests -t .` (Python core, including the coverage simulation) and `pnpm test && pnpm test:e2e` in `/web`.
3. Run the GeoLift comparison in [`/validation`](../validation/README.md).
4. Check the privacy claim yourself: open the app with your browser's network panel and run a plan. Only same-origin static files should load, and nothing should be sent.

Open an issue with your findings. We'll link it here whether or not we agree.

## Which version does a site run?

Every build of the web app writes `fosit-core.json` next to the app. It holds the engine fingerprint (`sha256` of the Python core bundle that does every calculation) and the git `commit` the build came from (`dirty: true` if it had uncommitted changes). The app's footer shows both. To check a site yourself:

1. Open `<site>/fosit-app/fosit-core.json` (or read the footer).
2. Check out that commit and run `python web/scripts/build_core_bundle.py`. The bundle is built reproducibly, so it prints the same `sha256` if the site runs that code.

As of 2026-11-16, the production site (adte.com) runs commit `6b59191` (engine `bcd3d3e4…`), the commit tagged `v0.1.0-review.1`. The staging site runs a later commit of main; its footer names it. A change to the screens only (nothing under `core/`) keeps the engine fingerprint, so compare the commit as well as the fingerprint.

## Open questions for reviewers

- The crossover (METHODOLOGY §14) assumes that the ads' effect fades within days. Its estimate is low even when that is true, and its range can miss the truth when it isn't (§14.5). Should the read correct for the locked half-life, report a sensitivity range, or refuse effects that last longer?
