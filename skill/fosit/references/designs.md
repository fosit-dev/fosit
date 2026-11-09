# Choosing a FOSIT design

Read this when recommending a design or answering "how should we test this?". Source of truth: `docs/METHODOLOGY.md` in the FOSIT repository.

## The three designs

### Geo cells (`--design cells`)
Each vendor gets its own small set of markets (default 3–15% of national sales per cell); everything else is a shared control that sees no test ads. A twin of each cell is built from the control markets.
- **Best for:** a clean vendor-vs-vendor comparison or a single channel test (`--cells 1`) where most of the country can go without the test media for a few weeks.
- **Trade-off:** only a small share of sales is "in test", so detectable lifts depend heavily on budget.
- Up to 6 cells.

### National holdout (`--design holdout`)
One campaign (one vendor, or several running together) runs everywhere except a planner-chosen holdout (default 10–20% of sales, at least 10 markets). A twin of the **holdout** is built from the markets with ads; the gap is the share of sales the ads drove, applied to the markets with ads.
- **Best for:** advertisers who won't switch CTV off in most of the country, or an always-on campaign.
- **The one rule:** during the history period the campaign must have been **off everywhere** (a launch) or **on everywhere** (always on). If it ran in only some markets, the twin learns a bent relationship: don't plan it; suggest a clean few weeks first.
- **Always-on:** held-out markets go dark at the test start; past ads keep working a while, so the result understates the campaign a little (cautious). Keep the holdout dark through the cooldown.
- Assumes the ads would have worked in the holdout like in the markets its twin leans on.

### Vendor split (`--design split --cells 2..4`)
Vendors split every market that isn't held out (for example 40% / 40%), and a no-CTV holdout (default 15–25% of sales) is the yardstick. Each vendor gets its own twin of the holdout, built only from its own markets; vendors are then compared head-to-head.
- **Best for:** "we want both vendors running at scale, and still know which one works".
- Same history rule as the national holdout.
- The split is balanced on sales and population; a single market with a large share of sales at an unusual rate per person can make every split fail the balance check: exclude it (`--exclude ID:reason`) or accept that no fair split exists.

## Geography (`--unit`)
- **`cbsa` (US metro and micro areas):** hundreds of markets, sharper tests. Vendors usually target these via ZIP lists. Prefer it.
- **`state`:** only 51 markets, so twins drift more and ranges are wider (FOSIT's placebo check widens them honestly). Use it when vendors can only target states.
- **`custom`:** the advertiser's own market IDs (e.g. DMAs via their own ZIP mapping). Nielsen DMA definitions are proprietary, so FOSIT doesn't ship them.

## Sizing
- **Test length:** compare 3/4/6/8 weeks (`--weeks`). Longer usually detects smaller lifts, but each extra week needs history to simulate, so on short histories longer tests can look *less* sensitive. Trust the table.
- **Cooldown:** 7 days by default (measured, no ads) to catch delayed purchases; 0 or 14 possible.
- **History:** 8 weeks minimum, 12+ recommended, up to 26 used (`--pre-weeks`).
- **Detectable iCPA** is the decision-maker's number: budget ÷ (detectable lift × baseline sales). If the vendor's realistic iCPA is better (lower) than this, the test should see the effect; if worse, expect "inconclusive". Levers: more budget, longer test, bigger cells / holdout, more history, metro areas.
- **Budget split** between vendors can be uneven; iCPA and iROAS always use actual spend.

## Small advertisers
At a few hundred orders a day, day-to-day chance is larger than 10% in a small group, so a daily fit score would reject every design. The planner then judges fit on weekly totals automatically (`plan --fit-period auto`, the default) and says so in `designs.md`; the plan locks that choice. Estimates and ranges stay daily, and placebo calibration keeps them honest. Expect larger detectable lifts: on synthetic data at 400 orders a day, about 24–28% for a 4-week test at $50k per vendor. More budget relative to sales, or a longer test, is the main lever. Don't hold out half the country just to pass a daily fit score.

## Exclusions
Leave out markets with something unusual during the test (a local promotion, store opening, a market a vendor can't reach): `--exclude ID:reason`. Excluded markets are dropped from the analysis entirely.

## Defaults worth knowing
Decision level 90% (95% also reported); moving-block conformal inference with placebo calibration (40 placebo cells); fit gate ≤ 10% holdout error; balance gate ≤ 10% gap; power target 80%; leakage warning above 5% of impressions outside assigned markets.
