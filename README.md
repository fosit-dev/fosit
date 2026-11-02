# FOSIT: Free Open-Source Incrementality Tool

**Don't trust any vendor. Including us. Check the math.**

FOSIT helps advertisers plan and read **geo-lift experiments** for CTV and other media you can't click. It tells you how many orders and how much revenue each vendor *actually caused*, what each extra order cost (iCPA), and the return per dollar (iROAS), with honest uncertainty. When the data can't tell, it says **"inconclusive."**

🔒 **Your data never leaves this browser.** All computation runs on your machine (Python via Pyodide, in a Web Worker). Nothing is uploaded, and a CI test fails if the app ever sends user data over the network.

> **Status:** pre-release. The statistical core, the GeoLift validation harness and the **Plan** module (web) are built and tested. The Read module is next.

## Why this exists

You own a restaurant. A flyer guy offers: *"Pay me $5 for every new customer who walks in holding my flyer."* Business looks great, until you step outside and see him handing flyers to people **already walking through your front door**. You weren't buying new customers. You were paying a toll on the ones you had.

Attribution reports often work like that flyer guy. Meanwhile CTV has the opposite problem: nobody clicks a TV, so click-based reports undercount it. FOSIT measures what matters, the customers who came in **because** of the ad, so you can invest in media like an investor and bring your CFO numbers that hold up.

## How it works

1. **Plan:** upload daily sales by market. FOSIT searches for fair splits of markets, one per vendor plus a shared no-ads control group. It shows how small a lift each design can detect, then **locks** the plan with a SHA-256 fingerprint you send to everyone before launch.
2. **Run:** each vendor targets only its own markets.
3. **Read:** upload sales through the end of the test and each vendor's spend and delivery. FOSIT builds a statistical twin of each cell from the control markets (augmented synthetic control), reports lift, iCPA, and iROAS with confidence ranges, compares the vendors head-to-head, and runs six honesty checks on every report.

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

Extension points are kept in `/core` (`design.py`, `estimators/`, `inference/`).

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
