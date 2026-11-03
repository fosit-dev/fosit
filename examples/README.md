# Examples with a known truth

Synthetic data on real US metro areas (Census CBSAs) and, for the national holdout, US states. **Not anyone's real sales.** Regenerate with:

```bash
python examples/generate_examples.py
```

(or `python examples/generate_examples.py national_holdout` for just that one).

| Folder | What's inside |
|---|---|
| `two_vendor/` | Vendor A's cell gets 1.5× its planned minimum detectable lift (MDE); Vendor B's gets 0.5× (low power: it may or may not be confirmed) |
| `null_effect/` | Same markets, no effect |
| `vendor_split/` | Two vendors ($200,000 each) split every state that isn't held out (§13.7). Vendor A gets 1.5× its planned MDE, Vendor B 0.5× |
| `national_holdout/` | One campaign ($400,000) on the 50 states + DC, running everywhere except a holdout chosen by the planner ([METHODOLOGY §13](../docs/METHODOLOGY.md#13-national-holdout)). The campaign states get 1.5× the planned MDE. Spend is spread by population; 0.5% can't be attributed to a state |

Each folder holds `history_for_planning.csv` (26 weeks before the test), `plan.fosit-plan.json` (locked the way the app does it: market search, then power), `kpi_history.csv` (through the cooldown), `spend_delivery.csv` ($50,000 per vendor, with 1.5% of Vendor A's delivery leaking into control markets and 0.5% of Vendor B's unattributable), and `truth.json`.

**How the truth is made:** the base data are generated once. The effect is then *added* as extra orders, Poisson(lift × that day's orders), in each cell's markets on ads-on days only. The history the plan was built on is untouched, and `truth.json` holds the exact orders and revenue added, which is what FOSIT estimates. The lift multiples and the random seed were fixed before looking at any result.

`tests/test_end_to_end.py` checks that the truth falls inside FOSIT's 90% intervals and that the null example is never called positive. `tests/test_holdout.py` does the same for `national_holdout/`. In the app, **Read → Try it with the example** loads `two_vendor/`, and **Try the national-holdout example** loads `national_holdout/`.
