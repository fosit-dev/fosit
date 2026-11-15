# Anatomy pictures: how a FOSIT test works

Read this when you explain a design, a plan or a result. Each picture shows the parts of the test with numbers. Fill in the real names, shares and dates, draw it in a code block, and then explain each number in one short sentence (see `writing.md`). Keep the picture under 72 characters wide so it fits a terminal.

The interactive page (`designs.html`, `plan.html`, `report.html`, or `fosit_cli.py anatomy`) shows the same anatomy with colors, and the reader can open each part. Send the file when the person will share it or come back to it.

## Geo cells (each vendor in its own markets)

```
 ① Split the markets          ② Run the ads          ③ Build a twin
 ┌──────────────────┐
 │ Vendor A   10%   │──── ads ───► real sales A ─┐
 ├──────────────────┤                            │ ④ compare
 │ Vendor B   10%   │──── ads ───► real sales B ─┤
 ├──────────────────┤                            │
 │ Control    80%   │──── no ads ► twin of A, ───┘
 └──────────────────┘              twin of B
                       ⑤ gap = extra orders (with a range)
```
1. FOSIT split the markets at random, and kept a split where the groups are alike.
2. Each vendor runs ads only in its own markets.
3. For each vendor, FOSIT mixes control markets into a twin that moved like the vendor's markets before the test.
4. During the test, FOSIT compares the real sales with the twin.
5. The gap is the extra orders. The range shows how sure the test is.

## National holdout (one campaign, a no-ads holdout)

```
 ① Hold out markets         ② Run the ads everywhere else
 ┌─────────────────────────┬──────────┐
 │ Campaign markets   85%  │ Held out │
 │ (ads)                   │ 15%      │
 └───────────┬─────────────┴────┬─────┘
             │ ③ twin of the     │ real held-out sales
             │   held-out markets│ (no ads)
             └────────► ④ compare ◄┘
      ⑤ the gap is the share of sales the ads drove
        × sales in the campaign markets = extra orders
```
1. FOSIT picked held-out markets at random. They get no ads.
2. The campaign runs everywhere else.
3. FOSIT mixes campaign markets into a twin of the held-out markets.
4. The twin shows the held-out markets *with* ads. Their real sales show them *without* ads.
5. FOSIT applies that share to the campaign markets to count the extra orders.

## Vendor split (vendors split the country, with a no-CTV group)

```
 ┌──────────────┬──────────────┬───────────┐
 │ Vendor A 40% │ Vendor B 40% │ No CTV 20%│  ① split
 └──────┬───────┴──────┬───────┴─────┬─────┘
        │ ③ twin of     │ ③ twin of    │ real sales, no CTV
        │  "No CTV"     │  "No CTV"    │
        │  from A only  │  from B only │
        └─► ④ compare ◄─┴─► ④ compare ◄┘
   ⑤ each vendor's share → its extra orders → compare the vendors
```

## Halves take turns (crossover, for small businesses)

```
 ① Two halves with the same sales: A ■  B □
 ② The ads move every 2 weeks, in a random order:
    weeks  1-2  3-4  5-6  7-8  9-10 11-12 13-14 15-16
    ads    B    B    A    B    A    A     B     A
 ③ skip the first 3 days of each block (ads still fade out)
 ④ in each block: half with ads vs half without ads
 ⑤ average the gaps; a test against every other fair order gives the range
```
This design assumes the ads' effect fades within days. If it lasts longer, part of it reaches the half without the ads, and the result is too low (METHODOLOGY §14.5).

## The timeline (any design)

```
 History (FOSIT learns)   Ads run          Cooldown     Read
 ├────── 8-26 weeks ──────┼── 3-8 weeks ───┼── 7 days ──┼──►
 Mar 9               Sep 6 Sep 7     Oct 4  Oct 11      from Oct 12
```

## Reading a result chart

```
 sales │      ① before: the lines      ② test: the gap is   ③ cooldown:
       │        move together            the effect          late orders
       │  ╱╲  ╱╲   ╱╲          ┆   ╱╲╱╲  ╱╲      ┆
       │ ╱  ╲╱  ╲_╱  ╲_  ╱╲    ┆  ╱    ╲╱  ╲____ ┆ ╲_
       │ ─ ─ ─ ─ ─ ─ ─ ─╲╱─ ─ ─┆─ ─ ─ ─ ─ ─ ─ ─ ─┆─ ─ ─   ── real sales
       │                        ┆                  ┆        ─ ─ twin
       └────────────────────────┴──────────────────┴──────► days
```
1. Before the test the real line and the twin move together: the twin is good.
2. During the test the gap between them is what the ads did.
3. During the cooldown the ads are off; FOSIT still counts late orders.

## The decision (is it worth the money?)

```
 cost per extra order:   $27 ├────●────┤ $56          ●  best estimate
 your value:                             ▲ $60        ├─┤ 90% range
 → the whole range is below $60: it pays off
```
Three outcomes: the whole range is below the value (pays off), the whole range is above it (does not pay off), or the value is inside the range (the test cannot tell).
