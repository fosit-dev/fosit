# UX flow and copy (v1)

**Status:** both modules are built in `/web`: Plan (screens 0 and P1–P7) and Read (R1–R6). FOSIT 0.1.0 is pre-release and not yet independently reviewed. Copy is editable; deviations from this draft are marked *(Built: …)*.

## Design principles

1. **First-timer first.** Someone who has never run a geo test can finish Plan in one sitting, without reading any docs.
2. **Depth on demand.** Every number and term has an **ⓘ** (plain-English tooltip, two sentences max). Every tooltip has **Read more →** (an anchor in METHODOLOGY.md) and, where relevant, **See the code →** (the exact function in `/core` on GitHub).
3. **No reasons to distrust.** No sign-up, no email gate, no upload, no tracking inside the tool, open source, reproducible, and a clear conflict-of-interest disclosure.
4. **Honest by default.** "Inconclusive" gets the same visual weight as a win. Warnings are never hidden behind toggles.
5. **Vendor-neutral.** The groups are "Vendor A / Vendor B" until the user labels them. No real vendor names anywhere in the UI, code, or defaults.
6. **The reader's level, in results and in planning.** A detail switch in the header (*Brief* for leaders, *Guided* for marketers, *Full* for analysts; `lib/level.tsx`) decides how much is shown. Brief: the answer, the money, the charts, and only the checks that did not pass. Guided (default): plus tables and explanations. Full: plus "In numbers" and the details open. Warnings and failed checks show at every level.
7. **Realistic, not fussy.** Never ask for data that would not change the answer: 8 weeks of history is enough, and 1–2 late days still read as final (METHODOLOGY §11.1).

## Writing

Answers, checklists and summaries follow the style of ASD-STE100 (Simplified Technical English): one idea per sentence (at most 25 words, 20 for an instruction), active voice, instructions that start with a verb, one word for one meaning (*extra orders*, *twin*, *range*, *held-out markets*), no idioms. The words that people read first (`core/fosit/explain.py`: the answer, the plan in short, who does what) are written once and shared by the web app, the PDF, the interactive pages and the agent skill. `tests/test_explain.py` checks the sentence lengths.

## Interactive pages

Plan, lock and read also produce one self-contained HTML file (`core/fosit/templates/page.html`, filled by `explain.render`): it works offline, makes no network requests and prints cleanly. It has the same Brief / Guided / Full switch, opening at the level the author chose.
- **Results:** the answer and what to do; "Is it worth the money?" (a slider for the value of one extra order, with each cost range as a bar); the anatomy of the test (numbered steps the reader can open); a chart per cell with hover values, numbered notes and a running total of extra orders; every check; all numbers at Full.
- **Plan:** the plan in short; the anatomy; a timeline (and the block schedule for a crossover); "Will the test see it?" (a slider for the expected cost of one extra order, read from the planning simulation's power curve in the appendix); "Who does what", with ticks the browser remembers; the market lists; the locked settings at Full.
- **Options** (skill `plan` step): each candidate design's share bar and its chance to see a given cost per extra order, by test length.

## Persistent elements (every screen)

- **Top banner:** 🔒 **Your data never leaves this browser.** ⓘ → "FOSIT runs entirely on your computer. Your files are read by your browser, and the math runs in your browser. Nothing is uploaded. Our automated tests fail if the app ever sends your data anywhere." · [How we test this →] (links to the CI privacy test in the repo)
- **Stepper:** `Why → Plan → Lock & share → (run your campaign) → Read`
- **Footer:** GitHub repo · METHODOLOGY.md · Review status (none yet), linking docs/REVIEW.md · Apache 2.0 · *optional, configurable:* "Questions? Contact us" · a version line: the FOSIT version, "pre-release, not yet independently reviewed", the engine fingerprint and the git commit the site was built from (from `fosit-core.json`)
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
3. **Read:** FOSIT compares each group with a twin (a mix of markets with no test ads that sells in step with the group). The gap is what the ads really did.

**See how a test works** *(Built 2026-11-16)*: four buttons (Compare two vendors · Test one campaign · A national campaign · A small business) switch a share bar with example sizes and the five numbered steps of that test (the same anatomy as Plan and the reports). Under the CTAs: "Never ran a test like this? FOSIT explains each step in plain words, with pictures. You do not need statistics."

**What you walk away with:** "What each vendor *really* delivered: the extra orders that its ads caused, the cost of one extra order and the return for each $1 of ads, each with an honest range. Invest in media like an investor, and bring your CFO numbers that hold up." *(The terms iCPA and iROAS are in the ⓘ.)*

**Trust strip:** 🔒 Runs in your browser · 📖 Open source (Apache 2.0) · 🧮 Every number shows its method · ✅ Checked against Meta's GeoLift on every code change · 🤷 "Inconclusive" is an allowed answer

**CTAs:** [Plan a test] (primary) · [I already have a locked plan → Read results] · [Try it with sample data]

---

## Plan module

*(Built 2026-11-16: the Plan screens adapt to the reader. This section describes what is built; the older draft is in the git history.)*

**The three levels in Plan** (the same switch as the reports, `lib/level.tsx`; the words are in `lib/words.ts`):

| | Brief | Guided (default) | Full |
|---|---|---|---|
| Questions | The fewest. FOSIT chooses test lengths (3, 4, 6, 8 weeks), cooldown (7 days), history (all of it, up to 26 weeks) and group sizes, and says what it chose. | The same, plus optional ones (advertiser, lengths, cooldown, history, group sizes). | Every setting, including how FOSIT judges chance and fit. |
| Explanation | One sentence. "How this test works" is folded away. | A 💡 line under each question says why FOSIT asks. Pictures are open. | As Guided. |
| Words | Plain. | Plain; a ⓘ gives the term for the person who wants it. | The technical names: cell, MDE, iCPA, iROAS, fit error, balance gap, pre-period. |
| Design cards | 3 designs, warnings only. | 5 designs, the checks as ✓ lines with the number. | 5 designs, chips with numbers, tables, power curves. |

Rules: a test-design term never shows at Brief or Guided unless the person opens a ⓘ. A term that belongs to one test type (blocks, held-out markets) shows only when that type is chosen. Warnings and blockers show at every level.

**Pictures** (`components/Visuals.tsx`; the reports draw the same ones):
- **Share bar:** the country as one bar, cut by share of sales. Color = a vendor's markets, gray = no ads. Example sizes before the search ("about 10%"), real sizes and market counts after it. The legend says the same in text.
- **Anatomy:** five numbered steps for the chosen test type, one sentence each; select a step to read more.
- **Timeline:** past sales, ads, cooldown, read, each as wide as it is long; it moves with the dates and lengths. A crossover adds the block strip.
- **Will the test see it?:** a slider for the expected cost of one extra order (or the return for each 1 of ads), and per vendor a meter with the chance in words. It starts at the person's own limit when they gave one.

### P1. Goal

- **"How much detail do you want?"** Brief · Guided · Full, each with what it means for planning.
- **"What do you want to find out?"** *Which vendor brings more extra sales?* (default) · *Do my ads bring extra sales?*
- **"How do you want to run the test?"** Three cards for the chosen question, each with a small share bar, one sentence, "Good for…", and at Full the technical name:
  - Compare vendors: **Each vendor in a few markets** *(Recommended; geo cells)* · **Vendors split the country** *(vendor split with a no-CTV holdout, §13.7; asks the number of vendors, 2–4)* · **More vendors, or my own settings** *(custom, up to 6)*.
  - One campaign: **Ads in a few markets** *(one cell)* · **Ads everywhere, except a small part** *(national holdout, §13)* · **Two halves take turns** *(geo crossover, §14)*.
- The two held-out designs ask right away: "In the weeks before the test, is this campaign running?" **No, it's off** · **Yes, everywhere** (note: the result is a little too low; keep the held-out markets dark through the cooldown) · **Yes, but only in some markets** (blocked: "FOSIT can't measure this cleanly…", with what to do instead).
- **How this test works:** the share bar with example sizes and the anatomy of the chosen type.
- **Help from a person** *(optional)*: when the deployment sets `VITE_CONSULT`, a "free analyst call" button sits in the header, and a short callout on the intro and on P1. On adte.com it opens the site's own contact form.

### P2. Your test

- Test name; advertiser (optional, not at Brief).
- Names: "Vendor 1 name", "Vendor 2 name" (Full: "Cell 1 name"), starting as `Vendor A`, `Vendor B`; one "Campaign name" for a one-campaign test. "FOSIT never knows who a vendor is, and it treats every vendor in the same way."
- Budget and currency; a split slider for two vendors (default 50/50) that shows each budget.
- "What do you count?" **Orders (or sign-ups, leads)** / **Revenue**.
- "What would make this worth it?" **I'm not sure yet** · **I know the most I can pay for one extra order** (Full: a target iCPA) · **I know the revenue I need for each 1 of ads** (Full: a break-even iROAS), each with an example.

### P3. Your sales history

- "What are the markets in your file?" **US metro areas** *(default; Full names the Census CBSA codes)* · **US states** · **My own list of markets**.
- Drop zone with a small picture of the file (three example rows) · [See the format] · [Download a template] · [Use sample data]. "Only have an order export with ZIP codes?" opens the orders helper.
- After parsing, a health card: "✓ 182 days (26 weeks) of history · ✓ 250 markets · ✓ Found: orders and revenue".
- **Small business hint:** at about 400 orders a day or less, with a test type other than "Two halves take turns", a note says that this type often cannot see a useful effect (below about 100 a day: usually no design passes), and offers to switch. For a vendor comparison it adds that the other test measures one campaign.

### P4. Markets

- ⚠️ **Targeting confirmation** (required before Lock, shown here first), worded for the test type.
- "Leave any markets out?": searchable list with an optional reason. "Most tests leave out none."
- Not at Brief: "How big can each vendor's group be?" (or "the part with no ads"), two sliders with a share bar that shows the middle of the limits. Open at Full.

### P5. Timing

- The timeline, at every level. A crossover adds the block strip with an example order.
- Brief: one sentence with what FOSIT chose. Guided and Full: test lengths to compare (3 / 4 / 6 / 8 weeks), cooldown, the weeks of past sales to learn from, with the "enough history" note (under 8 weeks: an error).
- A crossover asks "How long does your advertising keep working after it stops?" (a few days: 2-week blocks, 16 or 24 weeks; a week or more: 4-week blocks, 24 or 32 weeks), with the "Choose carefully" note at every level.
- Full only: "Advanced: statistics settings" (how to judge chance, how to judge a twin's fit, the seed).

### P6. Find markets (compute)

- Button: **Find fair market splits** / **Find a fair holdout** / **Find balanced halves**. Progress in plain words. Cancellable.
- Guided and Full: one line on what the search tried and kept.
- **Design cards**, each with the share bar (real market counts and shares):
  - Big line: "This test can see the ads if they raise sales by **6.5%** or more in each vendor's markets (4 weeks test)." (Full: "Can detect a lift of 6.5% or more in each cell".)
  - Money line: "In money: if one extra order costs more than **$84**, the test will probably miss the effect."
  - If the person's own limit is finer than the test: a warning that says so, and what helps.
  - On the chosen design: **Will the test see it?**
  - Checks: Guided "✓ The twin follows the real sales (4.1% off) · ✓ The groups are alike (3% apart) · ✓ No false alarms on past sales"; Brief shows only the ones that failed; Full shows "Fit error", "Balance gap" and the shares as chips.
  - Expand: the market lists and the chart of each group against its twin; at Full also the table, the balance by measure and the power curves.
- No design passed: what to try, in the person's words (for a small business: the other test type).

### P7. Lock & share

- The plan as a picture: the share bar (after the coin, if flipped), the timeline, and a table (who, budget, markets, share of your sales, the smallest rise in sales the test can see).
- Optional: 🪙 "Let a coin decide which vendor gets which group of markets?"
- Checklist (all required): each vendor confirmed its markets · dates and budgets are final.
- **Lock plan** → the fingerprint and short code, with one sentence on what the code proves, and **What happens next** (today: send the files; before the start: vendors set up; during: do not change the plan; after: come back to read).
- Downloads: **Plan PDF** · **Plan JSON** · **Interactive plan (HTML)** · [Copy email text] · "Include the planning details" toggle.
- "When the test is over, come back to <link>": the same link is in the email and the PDF and opens the tool on Read. [Go to Read results with this plan →] opens Read now, with the plan loaded.

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
Weights table (which control markets make up each twin), λ chosen, the placebo check (*Built:* how many placebo cells ran, whether they widened the range, and the placebo p-value; METHODOLOGY §5.6), placebo-in-time sensitivity check, permutation distribution plot, and links to the exact code.

### R6. Export
**Interactive report (HTML)** (see *Interactive pages*) · **CFO-ready PDF** (the answer first, checks, methods appendix, plan hash on every page) · **Results CSV** · **Analysis config** ("anyone can re-run this and get the same numbers").

*(Built: an "The answer" card comes before everything else: one headline, one detail and one "What to do" per cell, and the vendor comparison, from `explain.summary`. The older "Bottom line" sentences show as "In numbers" at Full.)*

---

## Tooltip style guide

- ≤ 2 sentences, no jargon in sentence one, numbers in examples.
- Example, **iCPA:** "What each *extra* order really cost: spend ÷ orders that wouldn't have happened without the ads. Lower is better."
- Example, **90% range:** "We're 90% confident the true value is in this range. If the range includes zero, we can't rule out that the ads did nothing."
- Example, **p-value:** "How often a gap this big shows up by pure chance when ads do nothing. Small (under 0.10) means it's unlikely to be luck."

## Accessibility and theming

WCAG 2.1 AA: 4.5:1 text contrast in both themes, full keyboard flow, verdicts never conveyed by color alone (icon + text), charts with data-table alternatives, tooltips reachable by keyboard and screen reader. Light and dark modes follow the system with a manual toggle. Mobile: single-column stepper. Heavy compute works on mobile but shows a "this may take a few minutes" note.
