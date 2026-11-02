# UX flow and copy (v1)

**Status:** both modules are built in `/web`: Plan (screens 0 and P1–P7) and Read (R1–R6). Copy is editable; deviations from this draft are marked *(Built: …)*.

## Design principles

1. **First-timer first.** Someone who has never run a geo test can finish Plan in one sitting, without reading any docs.
2. **Depth on demand.** Every number and term has an **ⓘ** (plain-English tooltip, two sentences max). Every tooltip has **Read more →** (an anchor in METHODOLOGY.md) and, where relevant, **See the code →** (the exact function in `/core` on GitHub).
3. **No reasons to distrust.** No sign-up, no email gate, no upload, no tracking inside the tool, open source, reproducible, and a clear conflict-of-interest disclosure.
4. **Honest by default.** "Inconclusive" gets the same visual weight as a win. Warnings are never hidden behind toggles.
5. **Vendor-neutral.** Cells are "Cell 1 / Cell 2" until the user labels them. No vendor names anywhere in the UI, code, or defaults.

## Persistent elements (every screen)

- **Top banner:** 🔒 **Your data never leaves this browser.** ⓘ → "FOSIT runs entirely on your computer. Your files are read by your browser, and the math runs in your browser. Nothing is uploaded. Our automated tests fail if the app ever sends your data anywhere." · [How we test this →] (links to the CI privacy test in the repo)
- **Stepper:** `Why → Plan → Lock & share → (run your campaign) → Read`
- **Footer:** GitHub repo · METHODOLOGY.md · Independent review (placeholder page) · Apache 2.0 · *optional, configurable:* "Questions? Contact us"
- **Disclosure line (footer):** "FOSIT was built by ADTE, a CTV platform. That's why it never knows which vendor is which, and why every line of it is public." *(Configurable. Shown when embedded on adte.com.)*

---

## Screen 0: Why this exists (first visit, skippable)

**Headline:** Don't trust any vendor. Including us. Check the math.

**The flyer story** (illustrated, ~30-second read):

> You own a restaurant. A flyer guy makes you an offer: *"Pay me $5 for every new customer who walks in holding my flyer."* Sounds fair. You only pay for results.
>
> Business looks great. Dozens of flyers a day. You're paying him more every week.
>
> Then one evening you step outside and see him standing **right at your front door**, handing flyers to people who were already walking in.
>
> You weren't buying new customers. You were paying a toll on the ones you already had.

**Then:**

> A lot of digital advertising is measured the same way: a platform gets credit for anyone who saw or clicked an ad, including people who were going to buy anyway.
>
> CTV has the **opposite** problem. Nobody clicks a TV, so click-based reports undercount it, and it gets cut even when it works.
>
> The only fair question is: **how many customers came in *because* of the ad?** That's **incrementality**.

**How FOSIT answers it (3 steps, icons):**

1. **Plan:** we pick groups of markets: one per vendor, plus a group that sees no ads. *(Like handing out flyers on some streets and not others.)*
2. **Run:** each vendor runs only in its own markets.
3. **Read:** we compare each group with a statistical twin built from the no-ads markets. The gap is what the ads really did.

**What you walk away with:** "What each vendor *really* delivered, in incremental orders, cost per incremental order (iCPA), and return on ad spend (iROAS), with honest ranges. Be a smart media-plan investor, and bring your CFO numbers that hold up."

**Trust strip:** 🔒 Runs in your browser · 📖 Open source (Apache 2.0) · 🧮 Every number shows its method · ✅ Checked against Meta's GeoLift on every code change · 🤷 "Inconclusive" is an allowed answer

**CTAs:** [Plan a test] (primary) · [I already have a locked plan → Read results] · [Try it with sample data]

---

## Plan module

### P1. Choose a template

Cards, first one preselected:

1. **Two-vendor test** *(Recommended)*: "Split one CTV budget between two platforms and find out which one really drives sales."
2. **Single-channel test:** "Is this channel driving incremental sales at all?"
3. **National campaign with a holdout:** "Keep the campaign running almost everywhere, leave about a tenth of the country without it, and measure what it really drives." *(Built. [METHODOLOGY §13](METHODOLOGY.md#13-national-holdout).)* Asks right away: "In the weeks before the test, is this campaign running?" **No, it's off** · **Yes, everywhere** (note: the result will be a little cautious; keep the holdout dark through the cooldown) · **Yes, but only in some markets** (blocked: "FOSIT can't measure this cleanly…", with what to do instead).
4. **Custom:** "Up to 6 cells, your own settings."

**National holdout differences in the later steps:** P2 has one "Campaign name" and a "Campaign budget during the test". P4 asks vendors to keep the held-out markets completely dark, and "Advanced" bounds the holdout's share of sales (10–20%). P6 is "Find a fair holdout": cards say "Can detect a lift of X or more in the campaign's markets", with chips for the share of sales held out and the number of markets held out vs. with ads; details compare the holdout with the markets with ads, and the chart shows the holdout's sales index vs. its twin. P7 asks the vendor(s) to confirm every held-out market stays free of ads until the cooldown ends; the email and plan PDF list the holdout first.

### P2. Your test

- Cell labels: `Cell 1`, `Cell 2` (editable). ⓘ "Name them however you like. FOSIT never knows who's behind a cell, and treats every cell exactly the same."
- Total budget + split slider (default 50/50) → shows each cell's budget.
- Currency (default USD).
- Primary goal: **Orders** / **Revenue** ⓘ
- *"What would make this worth it?"* (optional): target iCPA **or** break-even iROAS ⓘ "This lets FOSIT tell 'no lift worth paying for' apart from 'can't tell yet'."

### P3. Your sales history

- Geo unit first, because it decides which market IDs are valid: **Metro areas (Census CBSAs)** *(default)* · States · My own market IDs ⓘ. *(Built: moved here from P4.)*
- Drop zone: "Drop a CSV with daily sales by market" · [See the format] · [Download a template] · [Use sample data]
- Alternative link: "Only have an order export with ZIP codes? We'll turn it into markets for you." → orders-export helper.
- After parsing, a **plain-English health card**: "✓ 168 days (24 weeks) of history · ✓ 412 markets · ⚠️ We filled 1,204 missing market-days with 0 (normal for small markets) · ✓ Orders and revenue found." Each line has ⓘ.

### P4. Markets

- Exclude markets: searchable multi-select with reasons ("local promo", "store opening"…).
- Share of national sales per cell: min/max (3%–15%) under "Advanced".
- ⚠️ **Targeting confirmation** (required before Lock, shown here first): "Both vendors must be able to target exactly these markets. Confirm with each vendor before you lock the plan."

### P5. Timing

- Test length options to compare: 3 / 4 / 6 / 8 weeks (multi-select) · Cooldown: 7 days ⓘ · Planned start date.
- Pre-period auto-filled from the data with a gauge: <8 weeks red, 8–12 amber, 12+ green.

### P6. Find markets (compute)

- Button: **Find fair market splits**. Progress: "Searched 1,240 / 2,000 splits · Testing power on top 20 (7/20)". Cancellable. Results stream in.
- **Ranked design cards** (top 5, "show more"):
  - Big line: "**Can detect a lift of 6.5% or more** in each cell (4-week test)."
  - Money line: "If a vendor's true iCPA is worse than **$84**, this test probably won't see it."
  - Chips: Fit ✓ 4.1% · Balance ✓ 3% gap · 11% of national sales in test.
  - Expand: geo lists per cell, a balance table (cell vs. cell on volume, share, population, trend, seasonality), and a pre-period chart of each cell vs. its twin.
- **Power panel** for the selected design: power curve by lift (one line per duration) and power by budget for a hypothesized iCPA (slider). Each chart has ⓘ and "How we computed this →".

### P7. Lock & share

- Optional: 🪙 **Let a coin decide which vendor gets which market set.** ⓘ "Then neither vendor can say the other got the better markets."
- Checklist (all required): ☐ Cell 1's vendor confirmed they can target these markets · ☐ Cell 2's … · ☐ Dates and budget are final.
- **Lock plan** → shows the hash big: `9f2c 81ab …` + short code `9F2C81AB`.
- Downloads: **Plan PDF** (for everyone) · **Plan JSON** (to load at read time) · toggle "Include design diagnostics (shows your sales shares)".
- "**Now email the PDF, JSON and this code to the advertiser and both vendors, before launch.** That email is your proof the plan was set in advance." [Copy email text]

---

## Read module

### R1. Load
- *(Built: also "Try it with the example (two vendors, synthetic)", which loads `examples/two_vendor` from the app's own origin.)*
- Drop the plan JSON → "✓ Plan *Q4 CTV two-vendor test*, 2 cells, test Sep 1–28, cooldown to Oct 5."
- **Paste the code from your pre-launch email** ⓘ "This is what proves nobody changed the plan."
- Drop KPI file (through cooldown) and spend & delivery file. Health cards as in P3.

### R2. Honesty checks (shown first, always)
A row of six check tiles: Plan match · Pre-period fit · Geo leakage · Spend balance · Timing · Other changes. Each is pass ✓ / warn ⚠️ / fail ✕, with ⓘ and a one-line reason. "Other changes" asks the user to confirm (with an optional free-text note) before results are shown.

### R3. Results per cell
- **Verdict badge** (same size for all outcomes): ✅ Positive lift · ➖ No detectable lift · ❔ Inconclusive · ⚠️ Negative lift: investigate.
- One-sentence summary: "Cell 1 drove **1,840 incremental orders** (90% range: 950 to 2,700) at an **iCPA of $27** (range $19 to $53)."
- Chart: daily observed vs. twin, test window shaded, cooldown hatched, a band for the twin's uncertainty. *(National holdout: the chart shows the held-out markets (no ads) vs. their twin (with the ads), with a sentence explaining that the gap is applied to the markets with ads.)*
- Stats grid: Lift % · Incremental orders · Incremental revenue · iCPA · iROAS · p-value. Each shows estimate, 90% and 95% ranges, ⓘ, and Read more.

### R4. Head-to-head
- "**Cell 1 vs Cell 2:** iCPA $27 vs $41. Difference **−$14** (90% range: −$31 to +$6). → **Not distinguishable on this evidence.**"
- Standing caveat ⓘ: "The cells ran in different markets, so this compares vendor + markets. We balanced the markets to keep this fair."

### R5. Under the hood (collapsed)
Weights table (which control markets make up each twin), λ chosen, placebo-in-time sensitivity check, permutation distribution plot, and links to the exact code.

### R6. Export
**CFO-ready PDF** (verdicts first, checks, methods appendix, plan hash on every page) · **Results CSV** · **Analysis config** ("anyone can re-run this and get the same numbers").

---

## Tooltip style guide

- ≤ 2 sentences, no jargon in sentence one, numbers in examples.
- Example, **iCPA:** "What each *extra* order really cost: spend ÷ orders that wouldn't have happened without the ads. Lower is better."
- Example, **90% range:** "We're 90% confident the true value is in this range. If the range includes zero, we can't rule out that the ads did nothing."
- Example, **p-value:** "How often a gap this big shows up by pure chance when ads do nothing. Small (under 0.10) means it's unlikely to be luck."

## Accessibility and theming

WCAG 2.1 AA: 4.5:1 text contrast in both themes, full keyboard flow, verdicts never conveyed by color alone (icon + text), charts with data-table alternatives, tooltips reachable by keyboard and screen reader. Light and dark modes follow the system with a manual toggle. Mobile: single-column stepper. Heavy compute works on mobile but shows a "this may take a few minutes" note.
