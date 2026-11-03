# Reading and explaining FOSIT results

Read this before explaining a `read` report. The aim is a summary a CFO can act on and nobody can accuse of spin.

## Verdicts (per vendor/cell, at the plan's 90% level)

| Verdict | Means | Say it like |
|---|---|---|
| **Positive lift** | the whole 90% range of extra sales is above zero | "Vendor A drove about 1,240 extra orders (90% range 910 to 1,830), at roughly $40 per extra order." |
| **No detectable lift** | the range includes zero, and even its top is below what would have been worthwhile | "We can rule out an effect large enough to pay off." This is a real, useful answer. |
| **Inconclusive** | the range includes zero but also effects that would pay off; or the pre-period fit check failed | "The test can't tell either way." Explain why (small budget relative to sales, short test, noisy markets) and what would make the next test decisive. Don't hunt for a better cut. |
| **Negative lift: investigate** | the whole range is below zero | Unusual for advertising: check data problems, leakage, and the "other changes" answer before anything else. |

Always give the range with the number. The point estimate alone overstates certainty.

## iCPA and iROAS
- **iCPA** = spend ÷ extra orders. When the range of extra orders includes zero, iCPA has **no upper limit**: say "at least $X; we can't rule out zero extra orders", never a single number.
- **iROAS** = extra revenue ÷ spend (2.0 = each $1 brought back $2 that wouldn't have come otherwise).
- **Extra orders per 1,000 spent** is the safest comparison between vendors: it stays meaningful when one vendor's lift is near zero.

## Head-to-head
"Distinguishable from zero" means the data can tell the vendors apart; "not distinguishable on this evidence" means it can't, even if one point estimate looks better. Always add the standing caveat: **the vendors ran in different markets, so this compares vendor + markets** (FOSIT balanced the markets at planning time, which is why it's still fair, but not identical).

## Honesty checks (lead with any that aren't PASS)

| Check | If it warns or fails |
|---|---|
| **Plan match** | FAIL: the plan was changed after locking, or this isn't the plan from the email. The report is not the pre-registered analysis; say so first. WARN: no fingerprint given; ask for the one from the pre-launch email. |
| **Pre-period fit** | The twin didn't track the markets well before the test; affected cells are inconclusive by rule. |
| **Geo leakage** | Ads ran outside assigned markets (>5% of impressions): lift is biased toward zero, comparisons blurred. Name the vendor. |
| **Spend balance** | Actual split or delivery differed from plan; iCPA/iROAS use actual spend so they stay right, but sensitivity was lower than planned. |
| **Timing** | Read before the cooldown ended: INTERIM, numbers can still move. |
| **Other changes** | A promotion, price change, stock-out or other channel differed across markets: the ad effect is mixed with it. Never mark this as passed unless the person confirmed it. |

## For national holdouts and vendor splits
The effect is measured in the held-out markets (no ads) against a twin of them built from the markets with ads, and applied to the markets with ads. In words: "the held-out states sold X% less than they would have with the ads; applied to the states where the ads ran, that's N extra orders." If the campaign was always on before the test, add that the number is cautious (past ads keep working for a while after they stop).

## CFO summary template
```
## What we tested
<vendors / campaign>, <dates>, <markets>, <budget>. Plan locked and sent to all parties on <date> (fingerprint <short code>).

## What we found
<one line per vendor: verdict, extra orders with range, iCPA or iROAS with range>
<head-to-head line, with the markets caveat>

## How sure we are
<checks: all passed / which didn't and what it means>. Ranges are 90% confidence ranges; the method is open source and was fixed before launch.

## What it means for the budget
<decision implied by the target iCPA / break-even iROAS, or "not decisive; to get a decisive answer next time: …">
```

## Things not to do
- Don't round a range away or quote only the point estimate.
- Don't re-run with different markets, dates or KPIs to "check robustness" and then report the better one.
- Don't call a "no detectable lift" a failure of the test: it's an answer.
- Don't present synthetic examples as real results.
