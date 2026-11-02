# Examples with a known truth

Synthetic data on real US metro areas (Census CBSAs). **Not anyone's real sales.** Regenerate with:

```bash
python examples/generate_examples.py
```

| Folder | What's inside |
|---|---|
| `two_vendor/` | Vendor A's cell gets 1.5× its planned minimum detectable lift (MDE); Vendor B's gets 0.5× (low power: it may or may not be confirmed) |
| `null_effect/` | Same markets, no effect |

Each folder holds `history_for_planning.csv` (26 weeks before the test), `plan.fosit-plan.json` (locked the way the app does it: market search, then power), `kpi_history.csv` (through the cooldown), `spend_delivery.csv` ($50,000 per vendor, with 1.5% of Vendor A's delivery leaking into control markets and 0.5% of Vendor B's unattributable), and `truth.json`.

**How the truth is made:** the base data are generated once. The effect is then *added* as extra orders, Poisson(lift × that day's orders), in each cell's markets on ads-on days only. The history the plan was built on is untouched, and `truth.json` holds the exact orders and revenue added, which is what FOSIT estimates. The lift multiples and the random seed were fixed before looking at any result.

`tests/test_end_to_end.py` checks that the truth falls inside FOSIT's 90% intervals and that the null example is never called positive. In the app, **Read → Try it with the example** loads `two_vendor/`.
