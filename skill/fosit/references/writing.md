# Writing FOSIT answers in Simplified Technical English

Read this before you write a plan summary, a results explanation or an email. FOSIT answers follow the style of ASD-STE100 (Simplified Technical English): a controlled language made for readers who read fast or read English as a second language. This file gives the rules FOSIT uses and its own words list. It is not the official ASD-STE100 specification.

## The rules

1. **One idea per sentence.** Descriptions: 25 words or fewer. Instructions: 20 words or fewer.
2. **Active voice.** "The ads caused 1,240 extra orders." Not "1,240 incremental orders were driven."
3. **Simple tenses.** Present, past, future. Avoid "would have been", "is being".
4. **Instructions start with a verb.** "Send the plan file to each vendor." One instruction per sentence. Write steps as a numbered list.
5. **Warnings first.** Put the risk at the start: "Do not change the markets after the test starts. The result is then not the pre-registered analysis."
6. **Use articles and full words.** "Send the file to the vendor", not "Send file to vendor".
7. **No noun clusters of more than three words.** "the cost of one extra order", not "incremental order acquisition cost estimate".
8. **One word, one meaning.** Use the words list below every time. Do not change words for variety.
9. **No idioms, jokes or filler.** No "move the needle", "basically", "it's worth noting", "at the end of the day".
10. **Numbers with their range.** "About 1,240 extra orders (900 to 1,830)."
11. **Paragraphs of at most 6 sentences.** Use tables for comparisons.

## FOSIT words list

| Use | Meaning | Do not use |
|---|---|---|
| extra orders / extra revenue | orders or revenue the ads caused | incremental conversions, lift volume, uplift |
| lift | extra sales as a percent of sales without the ads | uplift, delta |
| twin | the mix of markets that shows sales without the ads | synthetic control, counterfactual (except for analysts) |
| range | the 90% confidence range | confidence interval (except for analysts), error bars |
| cost per extra order (iCPA) | spend ÷ extra orders | incremental CPA alone, without explanation |
| return per $1 (iROAS) | extra revenue ÷ spend | ROAS (that is a different number) |
| held-out markets | markets with no ads during the test | dark markets, control (in holdout designs) |
| control markets | markets with no test ads in a geo cells test | holdout (in a cells design) |
| the test cannot tell | the range includes zero and effects that pay off | inconclusive (except as the verdict name), failed |
| not enough effect to pay off | the test rules out an effect that pays off | no lift, failed |
| early read | a read before the planned end | interim (except for analysts) |
| fingerprint | the code that locks the plan | hash (except for analysts) |
| block | one 2- or 4-week period in a crossover test | phase, flight |

Explain a word the first time you use it, in one short sentence. After that, use it the same way.

## Examples

**Leader (brief).**
> Vendor A works. It brought about 1,240 extra orders at about $40 each (range $27 to $56).
> Vendor B also works, but its cost is not clear: $60 to $1,300 per extra order.
> The test cannot tell which vendor is better.
> **What to do:** Keep Vendor A. Give Vendor B a second, longer test before you spend more.

**Marketer (guided).**
> **The answer.** Vendor A brought about 1,240 extra orders (range 900 to 1,830). One extra order cost about $40.
> **How we know.** FOSIT built a twin of Vendor A's markets from markets with no ads. Before the test, the twin followed the real sales closely. During the test, real sales went above the twin. The gap is the extra orders.
> **What to do next.**
> 1. Compare $40 with the value of one order to you.
> 2. Open `report.html` and move the slider to that value.
> 3. Send the file to your team.

**Analyst (full).** Give the verdict and range for each cell, the cost range, the head-to-head interval and whether it excludes zero, the fit error against the locked limit, the placebo check, the leakage share and the method settings. Keep the same sentence rules.

## Before and after

| Before | After |
|---|---|
| "The 90% conformal interval for incremental orders excludes zero, indicating a statistically significant positive effect." | "The ads worked. The whole range of extra orders is above zero." |
| "We'd recommend potentially extending the test duration to improve statistical power." | "A longer test can give a clear answer. Six weeks instead of four sees a lift about 20% smaller." |
| "Please make sure that vendors are aware that targeting must be restricted." | "Tell each vendor to run ads only in its own markets." |
