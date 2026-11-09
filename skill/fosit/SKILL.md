---
name: fosit
description: Plan, lock and read geo-lift incrementality tests with FOSIT (Free Open-Source Incrementality Tool) — the honest way to find out what CTV, TV, audio, out-of-home or any click-less media really drives. Use this skill whenever someone wants to measure incrementality or lift, compare CTV vendors or platforms, test whether a channel "works", set up a holdout or a geo test, split markets between vendors, work out iCPA or iROAS, size a test or its budget, check a locked FOSIT plan, or read and explain FOSIT results to a CFO — even if they never say "FOSIT" or "geo-lift" (e.g. "is our CTV actually driving sales?", "which of these two vendors is better?", "we want to hold out some states").
---

# FOSIT: geo-lift tests, done by an agent

FOSIT measures how many orders (or how much revenue) a medium *caused*, by comparing markets that got the ads with a statistical "twin" built from markets that didn't. It plans fair market splits, **locks the plan with a fingerprint before launch**, and reads results with honest ranges, where "inconclusive" is an allowed answer. The engine is open source: <https://github.com/fosit-dev/fosit> (method: `docs/METHODOLOGY.md`).

Your job is to be the analyst who runs it: interview the person, prepare their data, run the engine through `scripts/fosit_cli.py`, and explain the output in plain English. The script does every calculation; you never compute lift, ranges or verdicts yourself, because a hand-rolled number would not be the pre-registered analysis.

## What makes FOSIT trustworthy (protect these)

- **The plan comes first.** Markets, dates, KPI, budget split and method are locked and fingerprinted *before* the money moves, then sent to everyone. After launch, never change markets, dates, the KPI or the method, never re-lock after seeing results, and never drop "weird" markets to improve a result. If someone asks, explain that this is exactly the freedom that lets any test say anything, and that the report would be marked *NOT THE PRE-REGISTERED ANALYSIS*.
- **Inconclusive is a real answer.** Don't soften it into a win, and don't go looking for a cut of the data that "works".
- **Vendor-neutral.** Cells are just labels. Recommend designs on fit, balance and sensitivity, never on who the vendor is.

## Before you open any data file: privacy

The FOSIT web app promises "your data never leaves this browser". When you work with it as an agent, **you (Claude) will see what you open**. So before reading any sales, order or spend file, say so plainly and offer the safer route. If you can't pause for an answer (for example, you were asked to just get it done), put this note at the very top of your reply instead, so it's the first thing they read:

- FOSIT only needs **daily totals by market** (date, market, orders, revenue). No customer names, emails or order-level detail.
- If they have an order-level export, run `orders` on it: the script aggregates it locally and you only see the summary it prints.
- Prefer the script's printed summaries to opening files. Don't print raw rows; inspect structure with the `check` command instead.

If they'd rather nothing leaves their machine, point them to the web app, which runs in the browser.

## Setup

```bash
python3 <skill-dir>/scripts/fosit_cli.py setup
```

The first run installs FOSIT's engine (pinned version) into `~/.fosit` and needs internet plus Python 3.12+ (or `uv`, which fetches Python itself). Run every command below the same way. Each prints a short Markdown summary and writes full outputs to files. Run `--help` on any command for every option.

## Planning a test

**1. Interview.** Ask only what you can't infer, a few questions at a time:
- What decision will this inform? (Which vendor to keep? Is CTV worth it at all? How much to spend?)
- Which vendors or campaigns, and the budget for the test period (and the split between vendors).
- The goal metric: orders (default) or revenue. Optional: a target iCPA or break-even iROAS, which lets FOSIT tell "not worth paying for" apart from "can't tell".
- Which geography the vendors can target exactly: US metro areas (`cbsa`, preferred, sharper tests), US `state`s, or their own market list (`custom`).
- When ads could start, and how long they could run (3, 4, 6 or 8 weeks).
- For any national/holdout design: in the weeks before the test, was the campaign **off everywhere**, **on everywhere**, or **on in only some markets**? The last one can't be measured cleanly: say so and suggest pausing or running everywhere for a few weeks first.

**2. Choose the design.** Read `references/designs.md` and recommend one:

| They want to… | Design | Command flag |
|---|---|---|
| compare vendors, each in its own small set of markets, with a large no-ads control | geo cells | `--design cells --cells 2` |
| keep one campaign national and hold out ~10–20% of the country | national holdout | `--design holdout` |
| have vendors split the country (e.g. 40% / 40%) with a no-CTV group (~20%) | vendor split | `--design split --cells 2` |
| measure one campaign for a **small business** (a few hundred orders a day or less) | halves take turns (crossover) | `--design crossover [--lingering long]` |

**3. Data.** They need daily sales by market for at least 8 weeks (12+ recommended, up to 26 used), ending just before the test. Formats and fixes: `references/data-formats.md`.

```bash
python3 scripts/fosit_cli.py check sales.csv --unit state
python3 scripts/fosit_cli.py orders orders_export.csv --unit cbsa --out sales.csv     # if they only have order exports
```

**4. Search designs.**

```bash
python3 scripts/fosit_cli.py plan sales.csv --unit state --design split --labels "Vendor A,Vendor B" \
  --budget 400000 --test-start 2026-03-02 --weeks 4,6 --out plan_work/
```

Present `plan_work/designs.md` in plain English: for the top 2–3 designs, how small a lift each can detect, the **detectable iCPA** ("if a vendor's true cost per extra order is worse than $X, this test probably won't see it"), the share of sales held out or in test, and fit. If even a vendor hitting their target iCPA would go undetected, say so and offer the levers: more budget, a longer test, bigger cells or holdout, more history, or metro areas instead of states. If no design passes, relay the script's advice.

**5. Lock.** Only after the person has chosen a design and length **and confirmed that every vendor can target exactly its markets** (and keep held-out markets dark):

```bash
python3 scripts/fosit_cli.py lock plan_work/ --choose 1 --weeks 4 --name "Q1 CTV vendor test" \
  --advertiser "Acme" --confirm-targeting [--ads-before off] [--basis target_icpa --target 40] [--coin-flip] \
  [--read-url <link to the FOSIT web app>]
```

`--coin-flip` lets a fair coin decide which vendor gets which market set, so neither can claim the other got better markets; offer it whenever there are two or more vendors. Hand over three files: the plan (`*.fosit-plan.json`), `plan-summary.md` (market lists per vendor) and `email.txt`. Tell them to **send all three, with the fingerprint, to the advertiser and every vendor before launch**: that email is the proof the plan came first. They keep the plan file for the read.

## Reading results

Gather, after the cooldown ends (an earlier read is marked INTERIM):
- the locked plan file, and the **fingerprint from the pre-launch email** (not from the file: the point is to prove the file wasn't changed);
- daily sales by market through the end of the cooldown, same format as for planning;
- spend & delivery by vendor (optional, but without it there is no iCPA/iROAS and no leakage check);
- the answer to: "During the test, did anything else change differently between the test markets and the rest? (a promotion, prices, stock-outs, another channel)".

```bash
python3 scripts/fosit_cli.py read plan.fosit-plan.json --sales sales_through_cooldown.csv --spend spend.csv \
  --fingerprint <from the email> --other-changes none --out results/
```

Then explain `results/report.md`, verdicts first. `references/reading-results.md` covers what each verdict and check means, how to word ranges honestly, and a CFO-ready summary template. If a check failed or warned, lead with it: it can change what the numbers mean.

To check a plan file on its own: `python3 scripts/fosit_cli.py verify plan.fosit-plan.json --fingerprint <hash>`.

## Trying it without real data

`python3 scripts/fosit_cli.py sample --unit state --out sample.csv` writes clearly synthetic sales data to plan with. The FOSIT repository's `examples/` folder has complete tests with a known truth (`two_vendor`, `national_holdout`, `vendor_split`), including plan, sales and spend files, to try `read` on. Always label synthetic results as synthetic.

## What FOSIT can't do (say so instead of improvising)

- **A past campaign that ran nationwide with no markets held out.** There's nothing running at the same time to compare against. Suggest a holdout for the next flight; at most offer a clearly labelled before/after read with another tool.
- **Customer-level or household holdouts, MMM, non-US geographies without a custom market file.**
- **Re-analysing after the fact with different choices.** That would not be the pre-registered analysis.

## Other ways in

- **The web app** (same engine, runs entirely in the browser, makes PDF plans and reports): the hosted version your team uses, or run it locally from the repository's `web/` folder.
- **Help from a person:** FOSIT is maintained by ADTE, a CTV platform (which is why it never knows which vendor is which, and why every line is public). ADTE's data analysts offer free planning calls via adte.com.
