# FOSIT: Free Open-Source Incrementality Tool

**Don't trust any vendor. Including us. Check the math.**

**Try it in your browser:** [adte.com/advertisers/incrementality-tool](https://www.adte.com/advertisers/incrementality-tool) (hosted by ADTE, the CTV platform that built FOSIT; no sign-up, and your files stay on your computer).

FOSIT helps advertisers plan and read **geo-lift experiments** for CTV and other media you can't click. It tells you how many orders and how much revenue each vendor *actually caused*, what each extra order cost (iCPA), and the return per dollar (iROAS), with honest uncertainty. When the data can't tell, it says **"inconclusive."**

🔒 **Your data never leaves this browser.** All computation runs on your machine (Python via Pyodide, in a Web Worker). Nothing is uploaded, and a CI test fails if the app ever sends user data over the network.

> **Status:** pre-release (0.1.0), **not yet independently reviewed** ([review status](docs/REVIEW.md)). Plan and Read are implemented for four designs (geo cells, national holdout, vendor split, halves taking turns) and tested end to end on synthetic data with a known truth ([`/examples`](examples), `tests/`, `validation/`). The geo-cells estimator is cross-checked against Meta's GeoLift in CI: the same estimates and p-values with matched settings (METHODOLOGY §12). The other designs rest on FOSIT's own simulations. Known limitations: [METHODOLOGY §15](docs/METHODOLOGY.md#15-known-limitations).

## Why this exists

You own a restaurant. A flyer guy offers: *"Pay me $5 for every new customer who walks in holding my flyer."* Business looks great, until you step outside and see him handing flyers to people **already walking through your front door**. You weren't buying new customers. You were paying a toll on the ones you had.

Attribution reports often work like that flyer guy. Meanwhile CTV has the opposite problem: nobody clicks a TV, so click-based reports undercount it. FOSIT measures what matters, the customers who came in **because** of the ad, so you can invest in media like an investor and bring your CFO numbers that hold up.

## How it works

1. **Plan:** answer a few questions in plain words, each with a picture (*Brief*, *Guided* or *Full* decides how many questions and how much terminology), and upload daily sales by market. FOSIT searches for fair splits of markets, one per vendor plus a shared no-ads control group. It shows how small a lift each design can detect, then **locks** the plan with a SHA-256 fingerprint you send to everyone before launch.
2. **Run:** each vendor targets only its own markets.
3. **Read:** upload sales through the end of the test and each vendor's spend and delivery. FOSIT builds a statistical twin of each cell from the control markets (augmented synthetic control), reports lift, iCPA, and iROAS with confidence ranges, compares the vendors head-to-head, and runs six honesty checks on every report. It starts with **the answer in plain words** and what to do, at the detail you pick (*Brief* for leaders, *Guided* for marketers, *Full* for analysts), and exports an **interactive HTML report** with pictures of how the test works and a slider for the value of one extra order, next to the PDF.

**Don't want to switch CTV off in most of the country?** A **national holdout** keeps one campaign running everywhere except about a tenth of the country, and measures what it drives from the markets left dark ([METHODOLOGY §13](docs/METHODOLOGY.md#13-national-holdout)). Or let **vendors split the country**, say 40% each, with a no-CTV group of about 20% as the yardstick ([§13.7](docs/METHODOLOGY.md#137-several-vendors-split-the-country)). **Small business?** Two halves of the country can **take turns** having the ads, which works down to about 50 orders a day ([§14](docs/METHODOLOGY.md#14-geo-crossover-for-small-advertisers)).

**Prefer to let Claude do it?** The [FOSIT skill](skill/README.md) lets Claude plan, lock and read tests for you with the same engine.

## Principles

1. **Vendor-neutral:** cells are user-labelled. Every cell runs the same code path. No vendor names in code or defaults.
2. **Client-side only:** no backend and no analytics inside the tool.
3. **Pre-registration:** the plan is locked and hashed before launch and checked at read time.
4. **Transparent and reproducible:** every number links to its method. "Inconclusive" is a first-class result. The core is validated against Meta's GeoLift (R) in CI.
5. **Apache 2.0.**

## Documentation

- [METHODOLOGY.md](docs/METHODOLOGY.md): the statistics, in plain English and in full
- [SCHEMA.md](docs/SCHEMA.md): input and output file formats
- [PREREGISTRATION.md](docs/PREREGISTRATION.md): how plans are locked, hashed, and verified
- [UX_FLOW.md](docs/UX_FLOW.md): screens and copy
- [CHANGELOG.md](docs/CHANGELOG.md)

## Repository layout

```
/core         Python: data prep, ASCM, conformal inference, market selection, power simulation, checks
/web          React app (Plan and Read modules), static build, embeddable via iframe
/schema       CSV specs (Frictionless Table Schema) + JSON Schema for the locked plan + validators
/validation   R harness that runs GeoLift on the same datasets
/examples     synthetic datasets (two-vendor scenario, null-effect scenario)
/tests        unit, coverage-simulation, end-to-end and privacy tests
/docs         methodology, schemas, pre-registration, UX, changelog
```

## Roadmap (beyond v1)

New designs follow the existing ones in `core/fosit/`: planning in `selection.py`, `power.py` and `crossover.py`; reading in `read.py`, `estimate.py`, `holdout.py` and `crossover.py`; one entry point for the app in `api.py`.

- **Rotation designs:** swap markets between cells in a second wave so head-to-head comparisons separate vendor from market
- Household-level holdouts (where a vendor supports them)
- Time-series-only reads without controls (clearly labelled as weaker evidence)
- Marketing mix modelling (MMM) calibrated with FOSIT experiment results
- Spillover-aware designs (commuting-zone buffers)
- More geo units (non-US)

## Who built this

FOSIT is built and maintained by [ADTE](https://www.adte.com), a CTV advertising platform, under a dedicated organization. Yes, we sell CTV. That's exactly why the tool never knows which vendor is which, runs the same code for every cell, locks the plan before launch, and puts every line of its math in public, so you don't have to take our word for anything. See [SECURITY.md](SECURITY.md) to report a privacy issue and [CONTRIBUTING.md](CONTRIBUTING.md) to help.

## License

[Apache License 2.0](LICENSE).
