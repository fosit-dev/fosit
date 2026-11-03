# FOSIT Methodology

**Status:** v1 draft for review (not yet implemented). Every number FOSIT shows links back to a section of this file.

**Who this is for:** each section opens with a short **In plain English** summary for marketers and finance teams, followed by the exact method for analysts and reviewers. You never need the second part to run a test. It's there so anyone can check our work.

---

## Contents

1. [The question FOSIT answers](#1-the-question-fosit-answers)
2. [Design: cells, markets, and dates](#2-design-cells-markets-and-dates)
3. [Data preparation](#3-data-preparation)
4. [The estimator: augmented synthetic control](#4-the-estimator-augmented-synthetic-control)
5. [Uncertainty: conformal inference](#5-uncertainty-conformal-inference)
6. [Business metrics: incremental orders, revenue, iCPA, iROAS](#6-business-metrics)
7. [Head-to-head: is the difference between cells real?](#7-head-to-head)
8. [Verdicts: positive, no detectable lift, inconclusive](#8-verdicts)
9. [Market selection (Plan)](#9-market-selection-plan)
10. [Power simulation (Plan)](#10-power-simulation-plan)
11. [Honesty checks (Read)](#11-honesty-checks-read)
12. [Validation against GeoLift](#12-validation-against-geolift)
13. [National holdout: the campaign runs everywhere except a few markets](#13-national-holdout)
14. [Known limitations](#14-known-limitations)
15. [Defaults reference](#15-defaults-reference)
16. [References](#16-references)

---

## 1. The question FOSIT answers

> **In plain English:** If you hadn't run these ads, how many of these orders would have happened anyway? The orders that wouldn't have happened are *incremental*. They're the only ones worth paying for.

Attribution (last click, view-through, platform-reported conversions) counts customers who *touched* an ad. Incrementality counts customers the ad *created*. The two can differ a lot:

- A platform can get credit for customers who were already on their way in. Think of a flyer vendor paid per customer holding a flyer, who hands flyers out at your front door.
- CTV and other media with no click (TV, audio, out-of-home) get *under*-credited by click-based attribution, so they get cut even when they work.

FOSIT estimates incrementality with a **geo experiment**. Ads run in some markets (treatment) and not in others (control). We then compare what happened in the treatment markets with a statistical "twin" of those markets built from the control markets.

**The causal quantity.** For treatment cell $k$ and measurement window $\mathcal{W}$ (test period plus cooldown):

$$\Delta_k = \sum_{t \in \mathcal{W}} \sum_{i \in T_k} \big( Y_{it}(1) - Y_{it}(0) \big)$$

where $Y_{it}(1)$ is the KPI in geo $i$ on day $t$ with the cell's ads running and $Y_{it}(0)$ is the KPI without them. We observe $Y_{it}(1)$ and estimate $Y_{it}(0)$.

---

## 2. Design: cells, markets, and dates

> **In plain English:** You split the country into groups of markets. Each vendor gets its own group. One shared group sees no test ads at all. That group is the yardstick.

- **Cell:** a set of treatment geos that receives one media treatment (for example, one vendor's CTV campaign). Cells have user-chosen labels. FOSIT never knows or assumes what a cell is. Every cell goes through exactly the same code path.
- **Control pool $C$:** geos that receive none of the tested media. All cells share it.
- **Excluded geos:** removed from the analysis entirely (for example, a market with a local promotion, or a market a vendor can't target).
- **Disjointness:** treatment sets are pairwise disjoint. The **treatment geos of any cell are never donors for another cell.** Each cell's synthetic control comes only from $C$.
- **Dates (locked in the plan):**
  - Pre-period `[pre_start, pre_end]`: history used to build the synthetic control. Warn below 8 weeks, recommend 12+.
  - Test period `[test_start, test_end]`: ads run.
  - Cooldown `(test_end, cooldown_end]`: ads are off and we keep measuring to capture delayed purchases. Default: 7 days.
  - Measurement window $\mathcal{W}$ = test period + cooldown.

**Other designs.** A **national holdout** turns this around: the campaign runs in almost every market and a few markets go without ([§13](#13-national-holdout)). Household holdouts are on the roadmap (see README).

---

## 3. Data preparation

> **In plain English:** We turn your sales data into one tidy table: one number per market per day. We tell you everything we had to fix.

1. **Validation** against [SCHEMA.md](SCHEMA.md). Hard errors stop the run. Warnings are shown and carried into the report.
2. **Order-level exports** (`order_date, shipping_zip, revenue`) are aggregated in the browser to `date × geo_id` using the ZIP→geo crosswalk ([§3.1](#31-geography)). Unmapped ZIPs are counted and reported, never silently dropped.
3. **Zero-filling:** if a geo appears anywhere in the file, missing `(date, geo)` rows inside the file's date range are filled with 0. The count of filled rows is reported because some exports omit zero days. A date missing for *every* geo is a hard error (data gap), not a zero.
4. **Aggregation level:** daily by default. If the median treated-geo daily KPI is very low (default: < 5 orders/day per cell), FOSIT suggests weekly aggregation. The choice is locked in the plan. With weekly data, conformal p-values have coarse resolution ([§5.4](#54-resolution-of-p-values)) and the UI says so.
5. **Donor screening:** control geos with zero KPI on more than 50% of pre-period days are dropped from donor pools (listed in the report). They still count as control geos, meaning nobody should target them.

### 3.1 Geography

- **Default unit: US Census CBSAs** (Core-Based Statistical Areas, OMB delineation, public domain). ZIPs outside any CBSA roll up to a `"{STATE}-NONCBSA"` unit per state. These units are eligible as controls but not as treatment by default, because vendors rarely target them cleanly.
- **Fallback:** US states (50 + DC).
- **Crosswalk shipped in repo** (`core/fosit/geo_data/`, rebuilt by `core/tools/build_geo_data.py`): the Census 2020 ZCTA→county relationship file plus the OMB July 2023 county→CBSA delineation (Bulletin 23-01). A ZCTA spanning several counties is assigned to the county with the largest land-area share. Connecticut's 2022 switch from counties to planning regions is handled with Census's 2022 town-to-ZCTA relationship file. Populations come from Census county estimates (Vintage 2025), summed to CBSAs and to each state's non-CBSA remainder. Puerto Rico and the territories are out of scope. ZIP and ZCTA are not identical, so PO-box-only ZIPs may be unmapped, and they're reported. Source URLs, vintages and SHA-256s are in `geo_data/SOURCES.json`. The mapping file's hash goes into every locked plan.
- **User-supplied mapping:** any `zip → geo_id` file (for example, an advertiser's own DMA mapping). FOSIT does **not** bundle Nielsen DMA definitions, because they are proprietary. The mapping file's SHA-256 is locked in the plan.
- **Targetability:** before locking, the user must confirm that **every cell's vendor can target exactly the chosen geo lists.** This is recorded in the plan.

---

## 4. The estimator: augmented synthetic control

> **In plain English:** For each cell we build a "twin" from a weighted mix of control markets. The twin is chosen so that, before the test, it moved exactly like the cell's markets. During the test, the twin shows what would have happened without the ads. A second step (ridge augmentation) corrects for any leftover mismatch in the twin.

We implement **ridge-augmented synthetic control (ASCM)** from Ben-Michael, Feller & Rothstein (2021), with unit fixed effects. This is the method Meta's GeoLift uses by default. We wrote it from the papers and did not port any code ([§12](#12-validation-against-geolift)).

### 4.1 Setup (one cell, one KPI)

- $T_0$ pre-period days, $T_1$ measurement-window days, $T = T_0 + T_1$.
- Treated series: the **average** across the cell's $n_k$ geos, $Y_{1t} = \frac{1}{n_k} \sum_{i \in T_k} Y_{it}$. We average rather than sum so the treated unit can sit inside the range spanned by individual donors. Totals are recovered by multiplying by $n_k$.
- Donors: $Y_{jt}$ for $j \in C$ (after screening, [§3](#3-data-preparation)), $J$ donors.
- **Fixed effects (demeaning):** each series has its pre-period mean subtracted, $\tilde Y_{jt} = Y_{jt} - \bar Y_{j,\text{pre}}$. This lets a small market serve as a twin for a large one if their *shapes* match. It matches GeoLift's default `fixed_effects = TRUE`.

Let $X_1 \in \mathbb{R}^{T_0}$ be the treated pre-period (demeaned) and $X_0 \in \mathbb{R}^{J \times T_0}$ the donors' pre-periods.

### 4.2 Synthetic control weights

$$\hat w^{\text{scm}} = \arg\min_{w \in \Delta^J} \; \lVert X_1 - X_0^\top w \rVert_2^2, \qquad \Delta^J = \{ w \ge 0, \textstyle\sum_j w_j = 1 \}$$

Solved as non-negative least squares (Lawson–Hanson active set, `scipy.optimize.nnls`), with the sum-to-one constraint enforced by one heavily weighted extra row. The data are rescaled first so the constraint dominates whatever the KPI's units. Unit tests check the result against an independent SLSQP solve. It takes about 4 ms for 600 donors. Implementation: `core/fosit/ascm.py::scm_weights`.

### 4.3 Ridge augmentation

A ridge regression of the measurement-window outcomes on pre-period outcomes, fitted across donors, estimates and removes the bias left by imperfect pre-period fit. With ridge regularization this gives closed-form **augmented weights**:

$$\hat w^{\text{aug}} = \hat w^{\text{scm}} + X_0 \left( X_0^\top X_0 + \lambda I_{T_0} \right)^{-1} \left( X_1 - X_0^\top \hat w^{\text{scm}} \right)$$

(with $X_0$ centered across donors). Augmented weights may be negative. That's the price of reducing bias, and the report shows how far they extrapolate (`sum of negative weights`).

**Choosing $\lambda$:** time-series cross-validation inside the pre-period. The grid has 20 values, geometric from the largest squared singular value of the centered donor matrix down to $10^{-8}$ of it (as in `augsynth`). The last 5 blocks of 7 pre-period days are held out one at a time. Each block is forecast from weights fitted on every earlier pre-period day (at least 28). We take the mean held-out squared error per $\lambda$, then apply the **one-standard-error rule**: the largest $\lambda$ within one SE of the minimum. $\lambda$ is selected once on the pre-period and held fixed for inference ([§5](#5-uncertainty-conformal-inference)). Implementation: `core/fosit/ascm.py::select_lambda`. A unit test confirms that the augmented-weights formula above equals the outcome-model form in Ben-Michael et al. (2021).

### 4.4 Counterfactual and effect

For every $t$:

$$\hat Y_{1t}(0) = \bar Y_{1,\text{pre}} + \sum_j \hat w^{\text{aug}}_j \tilde Y_{jt}$$

Effect on the average treated geo on day $t$: $\hat\tau_t = Y_{1t} - \hat Y_{1t}(0)$. Average effect over the window: $\hat\tau = \frac{1}{T_1}\sum_{t \in \mathcal W} \hat\tau_t$.

Orders and revenue are fitted **separately** (each KPI gets its own weights), because the best twin for order counts may differ from the best twin for revenue.

### 4.5 Pre-period fit

> **In plain English:** How closely did the twin track the real markets before the test? If it couldn't track them before, we can't trust it during.

$$\text{fit error (nRMSE)} = \frac{\sqrt{\frac{1}{T_0}\sum_{t \le T_0} (Y_{1t} - \hat Y_{1t}(0))^2}}{\bar Y_{1,\text{pre}}}$$

Reported per cell and per KPI, and checked against the plan's threshold ([§11](#11-honesty-checks-read)). We also report the **holdout** version used at planning time ([§9](#9-market-selection-plan)), which is a more honest measure because it isn't fitted on the days it scores.

---

## 5. Uncertainty: conformal inference

> **In plain English:** To decide whether a lift is real, we ask: "If the ads had done nothing, how unusual would this gap be?" We answer by shuffling time. We slide the whole timeline around and check how often a gap this big shows up by chance. No bell-curve assumptions.

We use the conformal inference procedure of Chernozhukov, Wüthrich & Zhu (2021), as implemented for ASCM in `augsynth` and used by GeoLift.

### 5.1 Testing a hypothesized effect

To test $H_0: \tau_t = \tau_0$ for all $t \in \mathcal W$ (a constant daily effect $\tau_0$ on the average treated geo):

1. Subtract the hypothesized effect: $Y^{(\tau_0)}_{1t} = Y_{1t} - \tau_0 \cdot \mathbb 1[t \in \mathcal W]$.
2. Refit the ASCM weights on **all $T$ periods** (pre and window), treating the adjusted series as untreated, with $\lambda$ held fixed.
3. Compute residuals $\hat u_t = Y^{(\tau_0)}_{1t} - \hat Y_{1t}(0)$ for $t = 1..T$.
4. Test statistic (two-sided, average effect): $S(\hat u) = \left| \sum_{t \in \mathcal W} \hat u_t \right|$. A one-sided variant ($-\sum$ or $+\sum$) is available and must be chosen in the plan.

   *Note on GeoLift.* An earlier draft of this document said this statistic matched GeoLift's `stat_test = "Total"`. **It doesn't.** GeoLift's two-sided statistic is $\sum_{t \in \mathcal W} |\hat u_t|$, the $q=1$ statistic of Chernozhukov et al. It tests "no effect on any day", so day-to-day noise counts against detection and it has much less power against a steady lift. Its test-inversion intervals can even exclude the point estimate. FOSIT's question is "did the ads add orders on average over the window?", which $|\sum \hat u_t|$ answers directly, and its calibration is verified (§5.5). `sum_abs` is available as an option and is what the GeoLift comparison uses (§12).
5. **Moving-block permutations** (default): for each shift $j = 0..T-1$, circularly shift the residual series, $\hat u^{(j)}_t = \hat u_{(t+j) \bmod T}$, and recompute $S$. Circular shifts keep autocorrelation intact, which is why we shift instead of shuffling individual days. See [§5.5](#55-permutation-scheme-why-moving-block) for why this is the default.
6. $p(\tau_0) = \frac{1}{T}\sum_{j=0}^{T-1} \mathbb 1\left[S(\hat u^{(j)}) \ge S(\hat u)\right]$. A shift counts when its statistic is at least the observed one, with a $10^{-9}$ relative tolerance for floating-point ties. A p-value equal to α is rejected.

The **p-value reported for a cell** is $p(0)$: how surprising the observed gap is if the ads did nothing.

### 5.2 Confidence intervals by test inversion

The $(1-\alpha)$ interval is the set of $\tau_0$ values that are **not** rejected: $\{\tau_0 : p(\tau_0) > \alpha\}$. We search a grid centered on $\hat\tau$, widen it until both ends are rejected, then refine each endpoint by bisection to a tolerance of 0.5% of the interval width. We report **90% and 95%** intervals. The plan locks which one drives the verdict (default 90%, $\alpha = 0.10$, matching GeoLift's default).

### 5.3 Assumptions (stated, not hidden)

Validity needs (a) the ASCM model to be approximately correct, so residuals are stationary and weakly dependent, and (b) no anticipation and no spillover from treatment into control geos. (a) is probed by the pre-period fit check. (b) is probed by the leakage check and the user's external-shocks confirmation ([§11](#11-honesty-checks-read)).

### 5.4 Resolution of p-values

With $T$ periods the smallest possible p-value is $1/T$. Daily data with 84 pre + 35 window days gives $1/119 \approx 0.008$. Weekly data with 16 pre + 5 window weeks gives $1/21 \approx 0.048$. Weekly designs can still clear $\alpha = 0.10$ but not by much, and the UI warns about this.

### 5.5 Permutation scheme: why moving-block

> **In plain English:** There are two ways to shuffle time. One is more likely to call a real effect a win. The other is right about how sure it is. We default to the one that's right about how sure it is, and we show the evidence.

The alternative is **iid permutations**: shuffle individual days at random, with 1,000 seeded draws. That's GeoLift's default (`conformal_type = "iid"`). It assumes residuals are exchangeable across days, which daily sales data usually aren't, because a good or bad week spills over into the next.

We measured both on 500 simulated panels with known truth. Each panel had 100 geos, 10 treated, 84 pre-period days, a 28-day test and 7 days of cooldown. Half had no effect and half had a 10% lift. Daily sales followed a latent factor model with persistent shocks (`core/fosit/synthetic.py`):

| Scheme | 90% interval covers truth | 95% interval covers truth | False positives at α = 0.10 |
|---|---|---|---|
| **Moving-block (default)** | **92.2%** | **95.4%** | **8.0%** |
| iid (1,000 draws) | 87.4% | 92.0% | 12.8% |

iid detects more lifts, but it overstates its certainty: about 1 in 8 null tests come out "significant" instead of 1 in 10. FOSIT's whole purpose is to be the number a CFO can trust, so **moving-block is the default.** iid stays available as a locked plan option for analysts who want GeoLift's default, and every report states which scheme was used. `tests/test_recovery.py` re-runs this comparison on every change (200 panels) and nightly (500).

**The cost is power, and here's why.** Under each hypothesis the model is refit on all $T$ periods, which exactness requires. The refit absorbs part of a real effect. In one diagnostic case, about 70% of a 20% lift was absorbed before the permutation step. Circular shifts that overlap the real window then look almost as extreme as the observed one. **A longer pre-period is the main lever:** in a 40-panel simulation, power to detect a 20% lift rose from 75% with 12 weeks of history to 100% with 26 weeks. FOSIT therefore recommends using up to 26 weeks of pre-period when the history allows.

### 5.6 Placebo calibration

> **In plain English:** Before trusting a range, we test the method on fake cells: groups of markets that got no ads, over the very same dates. If the method finds "effects" in those fake cells more often than it should, we widen the real range until it doesn't. Ranges only ever get wider, never narrower.

**Why.** Conformal inference (§5.1) is exact when the gap between a cell and its twin behaves the same in every stretch of time. Real twins drift: a cell and its donors respond a little differently to slow-moving shocks, and when the donor pool is small the twin can't fully cancel that. A slowly wandering gap is largest at the ends of the series, and the test window *is* the end of the series. So the post-period looks more extreme than a typical stretch for reasons that have nothing to do with the ads. We found this when planning on synthetic data exactly as the app does (market search, then the design with the best sensitivity): nominal 90% ranges held zero with no effect only **84%** of the time on state-level panels and **86%** on metro-level ones, with false "positive" verdicts at about **7–8%** instead of 5%. More history, a different ridge penalty and per-market linear trends did not fix it (per-market trends over-corrected, tripling the range).

**Procedure** (`core/fosit/placebo.py`). For each cell and KPI:

1. Draw $P$ placebo cells (default 40, locked in the plan as `method.placebo_calibration`), each a random set of markets from the cell's donor pool (the control markets; for a national holdout, the campaign markets on indexed series, §13.3) of the same size as the real cell (at most half the pool). Draws are seeded from the plan's seed, cell and KPI, so the read is reproducible.
2. For each placebo, build its twin from the rest of the pool with exactly the estimator of §4 (λ by cross-validation), fitted on the plan's pre-period, and record its mean error over the plan's measurement window divided by its pre-period residual SD: $z_p = \bar{\hat u}_{p,\mathcal W} / \mathrm{sd}(\hat u_{p,\text{pre}})$.
3. For level $1-\alpha$, let $q$ be the $\lceil (P+1)(1-\alpha) \rceil$-th smallest $|z_p|$ (infinite if there are too few placebos). The placebo range for the real cell is $\hat\tau \pm q \cdot \mathrm{sd}(\hat u_{\text{pre}})$.
4. **Report the hull** of the conformal range (§5.2) and the placebo range. The reported p-value is the larger of the conformal p-value and the placebo p-value $\big(1 + \#\{p : |z_p| \ge |z|\}\big)/(P+1)$, so it agrees with the range.

The power simulation (§10) applies the same rule: a placebo window counts as "detected" only if it also clears the placebo range, with $q$ computed from placebos over the most recent placebo window. So the planned MDE already includes this check.

**What it costs and buys** (`validation/calibration_study.py`, plans made exactly as in the app; with no effect and with lift = the planned MDE):

| Data · design | Covers zero, no effect: before → after (90% nominal) | "Positive", no effect: before → after (5% nominal) | Planned MDE detected, after (80% planned) | Median planned MDE, before → after |
|---|---|---|---|---|
| 51 states · two cells (200 panels, 386 cells) | 83.7% → **93.5%** | 7.3% → **2.3%** | 85.5% | 21.2% → 20.0% |
| 51 states · national holdout (200 panels) | 83.0% → **93.0%** | 7.5% → **1.5%** | 86.5% | 19.4% → 19.4% |
| 250 metros · two cells (60 panels, 120 cells) | 85.8% → **92.5%** | 8.3% → **5.8%** | 91.7% | 25.6% → 25.6% |
| 250 metros · national holdout (60 panels) | 85.0% → **88.3%** | 6.7% → **5.0%** | 90.0% | 20.6% → 30.0% |

The planned sensitivity barely moves on state data: the placebo range binds mostly in the null cases it was built for. The head-to-head (§7.2) was already conservative (its joint region covered the true difference 97% of the time on the state panels), so it is not recalibrated. Planning takes about twice as long (the placebo cells are extra fits).

Plans locked before this check existed (no `method.placebo_calibration`) are read exactly as locked, with plain conformal ranges, and the report says so.

---

## 6. Business metrics

> **In plain English:** We turn "the twin says sales would have been X" into money. How many extra orders and dollars, what each extra order cost (iCPA), and how many dollars came back per dollar spent (iROAS). Every number comes with a range, not just a single figure.

Per cell $k$ and KPI, with $\hat\tau$ and interval $[\tau_L, \tau_U]$ from §4–5:

| Metric | Estimate | Interval | Notes |
|---|---|---|---|
| Incremental orders / revenue | $\hat\Delta = n_k T_1 \hat\tau$ | $[n_k T_1 \tau_L,\ n_k T_1 \tau_U]$ | Totals over the measurement window |
| Counterfactual total | $\hat B = n_k \sum_{t\in\mathcal W} \hat Y_{1t}(0)$ | — | "What would have happened" |
| Lift % | $\hat\Delta / \hat B$ | $[\Delta_L/\hat B,\ \Delta_U/\hat B]$ | Counterfactual treated as fixed; documented simplification |
| Spend $S_k$ | Sum of the cell's spend in the spend file over $\mathcal W$ | — | Observed, no uncertainty. Includes spend that leaked outside the cell's geos, because it was still spent. |
| **iCPA** | $S_k / \hat\Delta_{\text{orders}}$ | $[S_k/\Delta_U,\ S_k/\Delta_L]$ if $\Delta_L > 0$ | If $\Delta_L \le 0$ the upper bound is **unbounded** and shown as "no upper limit: we can't rule out zero incremental orders." |
| **iROAS** | $\hat\Delta_{\text{revenue}} / S_k$ | $[\Delta_L/S_k,\ \Delta_U/S_k]$ | Can be negative |
| Incremental orders per $1,000 | $1000\,\hat\Delta_{\text{orders}}/S_k$ | linear in interval | Well-behaved even near zero. Used for head-to-head |

Mapping intervals through a monotone function (like $S/\Delta$) preserves coverage, so these intervals are exact consequences of the §5 intervals.

---

## 7. Head-to-head

> **In plain English:** Cell 1's iCPA was $42 and Cell 2's was $55. Is Cell 1 really cheaper, or could that gap be luck? We build a range for the *difference*. If the range includes zero, we say so plainly: on this evidence, you can't tell them apart.

### 7.1 What is compared

For every pair of cells $(a, b)$ and each KPI:

- **Δ iROAS** $= \text{iROAS}_a - \text{iROAS}_b$
- **Δ incremental orders per $1,000** (linear, always defined)
- **Δ iCPA** $= \text{iCPA}_a - \text{iCPA}_b$, plus the **iCPA ratio**. Reported with an interval when both cells' incremental-orders intervals exclude zero. Otherwise we show "not defined: at least one cell can't be distinguished from zero orders" and point to the orders-per-$1,000 comparison.

### 7.2 Method (our choice, and why)

**Choice: joint conformal confidence region, projected onto each comparison.**

The two cells share the same days, the same control pool, and the same national shocks, so their estimation errors are **correlated**. Treating them as independent would get the uncertainty of the difference wrong. Our approach keeps that correlation by permuting both cells **with the same time shift**:

1. For each cell, compute residual series $\hat u^{a}(\tau_a)$ and $\hat u^{b}(\tau_b)$ over a grid of hypothesized effects (the refits from §5.2, reused at no extra cost. Each cell's refit depends only on its own hypothesis, because the donor pools are the shared control geos only).
2. For each pair $(\tau_a, \tau_b)$, compute the joint statistic
   $$S_{\text{joint}} = \max\left( \frac{|\sum_{\mathcal W} \hat u^a_t|}{\hat\sigma_a},\ \frac{|\sum_{\mathcal W} \hat u^b_t|}{\hat\sigma_b} \right)$$
   where $\hat\sigma$ is each series' full-sample residual SD (the same under every shift, so the scaling doesn't change the permutation logic).
3. Apply the **same** permutation (circular shift $j$, or the same iid draw if the plan locks iid) to both residual series, recompute $S_{\text{joint}}$, and get $p(\tau_a, \tau_b)$ as in §5.1.
4. Joint $(1-\alpha)$ region: $R = \{(\tau_a, \tau_b) : p > \alpha\}$.
5. Interval for any comparison $f$ (Δ iROAS, Δ iCPA, ratio): $[\min_R f,\ \max_R f]$. Each cell's grid has 41 hypothesized effects spanning its 95% interval plus 25% on each side, so endpoints are accurate to about 1/40 of that span. Δ iCPA and the iCPA ratio are reported only if every point in the region has positive incremental orders for both cells. Implementation: `core/fosit/read.py::head_to_head`.

**Properties:** valid for all comparisons at once, preserves cross-cell correlation, and uses the same machinery as the per-cell results. Projection is **conservative**: intervals for the difference are somewhat wider than a test built for one specific difference. This is deliberate. FOSIT should be slow to declare a winner between two vendors.

**Considered and not chosen as primary:**

- *Placebo-in-time:* rerun the full analysis on fake test windows inside the pre-period and use the joint distribution of placebo "effects" as the error distribution. It's intuitive and keeps correlation, but a 12-week pre-period gives very few non-overlapping windows. It's shown under "Look under the hood" as a **sensitivity check** when there are at least 20 placebo windows.
- *Bootstrap over geos:* resampling geos breaks the synthetic-control structure (weights are fit to specific donors), and its validity for SCM isn't well established. Not used.

### 7.3 What a head-to-head difference does and does not mean

Cells run in **different markets.** A difference between cells is the difference of *(vendor × those markets)*, not of vendors alone. Market selection balances cells on volume, share of national sales, population, trend, and seasonality ([§9](#9-market-selection-plan)) to make this as fair as possible, but no design removes it fully. Every head-to-head report carries this sentence. A rotation design (swap markets in a second wave) is on the roadmap.

---

## 8. Verdicts

> **In plain English:** Every cell gets one of four labels. "No detectable lift" and "inconclusive" are different. The first means we can rule out an effect big enough to matter. The second means the test can't tell either way. Both are honest answers, and both are useful.

The decision level $\alpha$ (default 0.10) and the **meaningful effect** $\delta^*$ are locked in the plan. $\delta^*$ is the incremental-orders (or revenue) total that would hit the user's **target iCPA** (or **break-even iROAS**), computed from the cell's actual spend: $S_k / \text{target iCPA}$ orders, or $S_k \times$ break-even iROAS revenue. If the user gives neither, $\delta^*$ is the cell's **planned MDE** (`decision.planned_mde_lift`, locked in the plan so it can't be redefined after the results are in) times the twin's counterfactual over the ads-on days.

| Verdict | Rule (using the $(1-\alpha)$ interval $[\Delta_L, \Delta_U]$) |
|---|---|
| **Positive lift** | $\Delta_L > 0$ |
| **Negative lift**, investigate | $\Delta_U < 0$ (unusual for ads. Check for data or leakage issues.) |
| **No detectable lift** | $\Delta_L \le 0 \le \Delta_U$ **and** $\Delta_U < \delta^*$: any lift is too small to meet the target |
| **Inconclusive** | $\Delta_L \le 0 \le \Delta_U$ **and** $\Delta_U \ge \delta^*$: the test can't rule out a worthwhile effect. **Or** a blocking honesty check failed ([§11](#11-honesty-checks-read)). |

Head-to-head verdict: "**{a} vs {b}: distinguishable**" if the Δ interval excludes zero, otherwise "**not distinguishable on this evidence**."

**Multiplicity:** the plan names one **primary** metric (default: head-to-head Δ iCPA on orders, or Δ iROAS if revenue is primary). Everything else is labelled *secondary*. We don't adjust secondary intervals, and we say so.

---

## 9. Market selection (Plan)

> **In plain English:** We search thousands of ways to split your markets into one group per vendor plus a shared control group. We keep the splits where (1) each group's twin tracks it well, and (2) the groups are fair to each other: similar size, similar share of your sales, similar population, similar trends. A fair split matters as much as a precise one. Otherwise the "winning" vendor might just have had the better markets.

### 9.1 Inputs

KPI history, number of cells $K$ (default 2), excluded geos, per-cell share-of-national-KPI bounds $[s_{\min}, s_{\max}]$ (defaults 3%–15%), minimum control share (default 50% of national KPI), geo attributes (population, from Census, or user-supplied).

### 9.2 Candidate generation: stratified randomized search

1. Compute per-geo features over the pre-period: KPI share of national, population, trend (last-4-weeks ÷ first-4-weeks), seasonality correlation with the national series, and revenue per order (if revenue exists).
2. Sort eligible geos by KPI volume and form **strata** of $K+1$ adjacent geos (similar size).
3. To build one candidate design: draw a target share per cell in $[s_{\min}, s_{\max}]$. Pick strata at random (weighted toward mid-sized geos with good individual fit). In each chosen stratum, **randomly** assign one geo to each cell and leave the rest in control. Stop when every cell reaches its target share.
4. Repeat with a seeded RNG (default 2,000 candidates). The seed is locked in the plan, so anyone can regenerate the same candidates.

Randomizing within strata gives balance by construction and means **no one hand-picked the markets.** It also limits overfitting to noise in the pre-period.

### 9.3 Scoring

- **Eligibility:** a geo can be a treatment candidate only if it isn't excluded, is treatment-eligible (non-CBSA remainders aren't by default), has nonzero KPI on at least half the pre-period days, and holds at most half of $s_{\max}$ on its own, so no single market dominates a cell.
- **Fit (holdout):** for each cell, fit on the pre-period minus its final $H$ days ($H$ = shortest planned test length), forecast those $H$ days, and compute nRMSE. The holdout keeps us from rewarding designs that only *look* good in-sample. For speed this runs in two stages. Every candidate that passes the share and balance gates is screened with plain synthetic control. The best 60 are then re-scored with full ASCM (λ by cross-validation), and that score is the one reported and gated.
- **Balance:** for each feature, the relative gap between cells, $|f_a - f_b| / \text{mean}(f_a, f_b)$ (for $K>2$, max over pairs). Balance score = the largest gap. Default gate: ≤ 10%.
- **Gates:** share bounds, control share, fit ≤ threshold (default holdout nRMSE ≤ 10%), balance ≤ 10%.
- **The Read check's limit.** For the shortlisted designs we also compute the **in-sample** fit over the whole pre-period, which is exactly what the Read module's pre-period fit check recomputes (§11). The plan locks a limit of 1.5 × the worse of the two fits, capped at 15%. Using the holdout fit alone set limits that a perfectly good design could miss at read time, because the two measure different things (on state-level holdouts the in-sample fit over 18–26 weeks ran higher than the 4-week forecast fit); with the in-sample fit included, the check fires when the data or the markets' behaviour really changed.

### 9.4 Ranking

Designs passing all gates are shortlisted (top 20 by `max cell holdout nRMSE`, ties broken by balance). The top 5 run the power simulation (§10). The final list is ranked by **worst-cell MDE** at the shortest planned duration (a head-to-head is only as sensitive as its weakest cell), with any design that fails the calibration check (§10.1 step 7) ranked last. Each design shows fit, balance, MDE, and the share of national sales in test (the opportunity cost of the test).

Expect the fit score to favour larger cells, because averaging more markets smooths noise. That's a real trade-off against the share of sales held out of business-as-usual, so the UI shows both side by side and doesn't hide it in the ranking.

### 9.5 Optional: coin flip for vendor-to-cell assignment

After the user picks a design, FOSIT can randomly decide which label goes to which market set (cryptographic RNG, result recorded in the plan). That way neither vendor can claim the other got the better markets.

---

## 10. Power simulation (Plan)

> **In plain English:** Before spending a dollar, we replay your past data many times and pretend the ads worked by a known amount. If the method catches a 5% lift in 80 out of 100 replays, the test can "see" 5%. The smallest lift it reliably catches is the minimum detectable effect (MDE). Then we translate it into money: "if a vendor's true iCPA is worse than $X, this test probably won't see it."

### 10.1 Procedure

For a design, each cell, each candidate duration $D$ (default options: 3, 4, 6, 8 weeks, plus cooldown):

1. **Placebo windows:** choose start dates for windows of length $D$ + cooldown in the historical data, latest first, 7 days apart so each starts on the same weekday. Each window gets a pre-period before it. For each test length $D$ we use the longest pre-period, up to the planned one, that still leaves **6 weeks of history spare**, never shorter than 8 weeks. That gives up to 7 placebo windows. The trade-off is deliberate: more windows make the power estimate more reliable, a longer pre-period makes it more realistic, and a shorter simulated pre-period makes the MDE conservative (§5.5). The UI shows the history length behind each estimate. λ and the pre-period fit are computed once per window, because injecting an effect into the window doesn't change them.
2. **Inject** a multiplicative lift $e$ into the cell's geos during the test portion of the window: $Y_{it} \leftarrow Y_{it}(1+e)$, with no lift during cooldown (conservative).
3. **Run the full read pipeline** (ASCM + conformal p-value, §4–5) with **exactly** the estimator and $\alpha$ that will be locked for the real read. Power simulation never uses a shortcut estimator, so the MDE is honest about the real test.
4. Detected = $p(0) \le \alpha$ and the estimate has the correct sign.
5. Power$(e, D)$ = share of windows detected. Effect grid: 0%, then a coarse grid (2.5%, 5%, 10%, 15%, 20%, 30%) refined by bisection around the 80% crossing.
6. **MDE** = smallest $e$ with power ≥ 80% (configurable).
7. **Calibration check:** power at $e = 0$ is the false-positive rate and should be close to $\alpha$. With few windows a single false hit is common by chance (1 of 7 is 14%), so the design is flagged only when the count is surprising for a calibrated test. That means a one-sided binomial test, $P(X \ge k \mid n, \alpha) < 0.05$: with 7 windows at α = 0.10, 3 or more false hits. Flagged designs are ranked last and labelled "Found fake lifts in past data".

With at most 7 windows, power estimates are coarse (one window is about 14 points), and overlapping windows are correlated. The UI shows the number of windows behind each estimate. This is a property of the data available, and we don't hide it.

### 10.2 From MDE to money

For cell $k$ with planned budget $B_k$ and baseline KPI $\bar B_k(D)$ over the $D$ test days, estimated as the cell's average daily total over the last 28 days of history times $D$. The MDE is a lift *during the ads-on days*; cooldown days are measured but get no injected lift:

- **MDE in orders:** $M_k = e^*_k \cdot \bar B_k(D)$
- **Detectable iCPA:** $\text{iCPA}^*_k = B_k / M_k$. "If this vendor's true iCPA is above **$iCPA\*$**, this test will probably *not* detect it."
- **Detectable iROAS:** $M^{\text{rev}}_k / B_k$.

**Power by budget:** assume incremental orders scale linearly with spend at a hypothesized true iCPA $c$ (no saturation in the tested range). Then lift $e(B) = (B/c)/\bar B_k(D)$ and power comes from the effect curve with **no extra simulation**. The linearity assumption is stated next to every budget curve.

### 10.3 Runtime

The total is about (shortlisted designs × cells × durations × effects × windows) ASCM refits. In Pyodide we expect minutes, not seconds. Results stream in progressively, the run can be cancelled, and the UI always shows what's done.

---

## 11. Honesty checks (Read)

> **In plain English:** Before you believe any result, these checks ask: did anyone change the plan, did the twin fit, did ads leak into the wrong markets, was the money split as agreed, did we look too early, and did anything else change? They appear on every report, including the PDF.

| Check | Pass | Warn | Blocking? |
|---|---|---|---|
| **Plan match** | Plan hash recomputed from the loaded plan equals the hash shared before launch (user pastes it), and all analysis inputs (geos, dates, KPI, method) come from the plan | Any mismatch. The report shows a field-by-field diff when the original plan is available and is watermarked "NOT THE PRE-REGISTERED ANALYSIS." | Watermark, verdicts kept |
| **Pre-period fit** | Each cell's pre-period nRMSE ≤ the plan's threshold | Above threshold | Cell verdict → **Inconclusive** |
| **Geo leakage** | ≤ 5% of a cell's impressions outside its assigned geos | > 5%. Shown split into: in control geos, in another cell's geos, outside the study, unknown geo (`*`) | No (warn). Leakage into control biases lift **toward zero**. Leakage into another cell contaminates the comparison. Both are explained. |
| **Spend balance** | Realized spend share within ±5 points of planned share, and each cell ≥ 90% of planned budget | Outside either bound | No (warn). iCPA/iROAS already use actual spend. |
| **Early read** | Data covers through `cooldown_end` and read date ≥ `cooldown_end` | Earlier | No. Report labelled **INTERIM** and conformal windows truncated to available days. |
| **External shocks** | User confirms no other channel, promotion, pricing, or stock change differed across cells or vs. control | Not confirmed, or user describes a change (free text goes into the report) | No (warn) |

Unknown-geo impressions (`geo_id = *`) count as **unverifiable**, not as leakage, and are shown separately.

---

## 12. Validation against GeoLift

> **In plain English:** We didn't just write our own math and hope. We run the same datasets through Meta's open-source GeoLift (in R) and check that our answers match within stated tolerances. The check runs automatically on every code change.

- **Independence:** FOSIT's core is written from the papers in [§16](#16-references). No GeoLift or `augsynth` source is copied, and none ever will be. GeoLift's licensing is ambiguous: GitHub's license detection lists MIT, but the package's DESCRIPTION file says GPL (≥ 2), and GPL code can't be folded into an Apache-2.0 project. `augsynth` is MIT. Both are used only as external black boxes in CI.
- **Harness:** `/validation` generates deterministic synthetic cases (null effects, 10% and 20% lifts, a single-geo test). It runs `GeoLift::GeoLift()` on each with `model = "Ridge"`, `fixed_effects = TRUE`, `stat_test = "Total"`, `conformal_type = "block"` (GeoLift's own default is `"iid"`, see §5.5), `grid_size = 250`, α = 0.10 and `ConfidenceIntervals = TRUE`. A GitHub Actions job (`.github/workflows/validation.yml`) compares the outputs to FOSIT's. GeoLift and augsynth are pinned to exact commits, and the job runs on R 4.5. augsynth is pinned to the version current when GeoLift was last updated (March 2026). Later augsynth releases changed internals GeoLift calls, and GeoLift crashes with them. Bumping either pin is a deliberate change logged in the CHANGELOG.
- **Two comparisons per case** (`validation/compare.py`):
  1. **Matched (gating).** FOSIT runs with GeoLift's selected λ *and* GeoLift's test statistic (`sum_abs`). Same model, same test, so every number must agree. This validates the estimator and the conformal engine.
  2. **Defaults (informational).** Each tool uses its own defaults, side by side, with each one's error against the known truth. They differ by design: FOSIT picks λ with 7-day held-out blocks and tests the average effect; GeoLift picks λ with 1-day holdouts and tests every day. This table never fails the job.
- GeoLift searches interval bounds on a fixed grid (mean ATT ± 6 × RMS of the post-period ATT, 250 points) and falls back to jackknife+ when no grid point is accepted. Bounds at the grid edge, or from the fallback, aren't conformal bounds, so they're skipped and reported.

| Quantity (matched comparison) | Tolerance |
|---|---|
| Percent lift | ±0.25 pp absolute |
| ATT (avg daily effect) | ±1% relative |
| CI bounds | ±5% of GeoLift's CI width (its grid step is about 2% of a typical width) |
| p-value | ±0.02, and same side of α |

**Results (CI run 6, GeoLift 2.7.5 at db34ea4, augsynth 65c5a6f, R 4.5; all gating checks pass):**

- *Matched (same λ, same statistic):* lift and ATT agree to within 1e-5 relative in all six cases, and the counterfactual to within 0.004% of the daily level. **p-values are identical in all six cases.** Where GeoLift's interval is a real conformal bound (3 cases), FOSIT's bounds agree within 0.2–1.4% of the interval width, inside GeoLift's own grid resolution. In the other 3 cases GeoLift's interval runs into its search limit and FOSIT's is unbounded: both tools are saying the same thing, "very wide".
- *Defaults (informational), against the known truth:*

| Case | True effect | FOSIT p-value | GeoLift p-value | FOSIT 90% CI covers truth | GeoLift 90% CI covers truth |
|---|---|---|---|---|---|
| lift10_a | +10% | **0.017** | 0.68 | yes | yes |
| lift10_b | +10% | **0.050** | 0.34 | yes | yes (±70 per day: uninformative) |
| lift20_a | +20% | **0.034** | 0.83 | yes | yes (±65 per day: uninformative) |
| null_a | none | 0.008 (false positive) | 0.79 | no | yes |
| null_b | none | 0.54 | 0.87 | yes | yes |
| single_geo | +15% | 0.11 | 0.14 | yes | yes |

  FOSIT's defaults detected all three real effects at α = 0.10, and GeoLift's detected none. In 3 of 6 cases GeoLift's cross-validation picked a near-zero λ (≈0.01), which lets the ridge step overfit so the conformal refit absorbs the effect. FOSIT's 1-SE rule kept λ large; on lift10_b that gave an estimate 6× closer to the truth. FOSIT produced one false positive in two nulls. That's consistent with its measured 8% rate over 500 simulations (§5.5), but it's a real example, and it's why the honesty checks and pre-registered thresholds exist. Six cases are an illustration; the calibration evidence is the 500-panel simulation.

These tolerances are **provisional**. They'll be tightened or justified after the first harness runs, and every change is logged in [CHANGELOG.md](CHANGELOG.md).

**Also tested (in `/tests`):**
- SCM weights vs. an independent QP solve on small problems. Ridge step vs. a closed-form reference.
- Conformal p-values on constructed series where the answer is known.
- **Coverage simulation:** 500 synthetic panels with known effects (nightly; 200 on every change). Nominal 90% intervals must cover the truth 86–94% of the time. **Current result: 92.2% (90% intervals), 95.4% (95% intervals), 8.0% false positives at α = 0.10** (§5.5).
- **End-to-end** (`tests/test_end_to_end.py`, data from `examples/generate_examples.py`): the two-vendor example's true incremental orders, revenue and iCPA all fall inside the 90% intervals. The cell given 1.5× its planned MDE is called "positive". The null example returns "no detectable lift" or "inconclusive" for both cells, never "positive", and no head-to-head difference is called distinguishable. The effect is *added* to the same base data the plan was built on (extra orders drawn on ads-on days), so the truth is the exact number of orders added. Current run: Vendor A 1,242 estimated vs 1,321 true (90%: 913–1,834); Vendor B 449 vs 446 (90%: 37–839).

---

## 13. National holdout

> **In plain English:** Most advertisers don't want to switch CTV off in most of the country. A national holdout keeps the campaign running nearly everywhere and leaves about a tenth of the country without it. FOSIT builds a twin of those dark markets from the markets that kept the ads, which shows what the dark markets would have sold *with* the ads. The gap is what the ads were worth, and it's applied to the markets that ran them.

### 13.1 When to use it, and the one rule

Use it to measure **one campaign** (one or several vendors together) that runs nationally. Use geo cells (§2) to compare vendors.

The plan has one cell, the **campaign markets** (every market not held out or excluded), and the control pool is the **holdout**: markets the campaign must not reach during the test and cooldown.

**The rule:** during the history period the holdout and the campaign markets must have had the *same* exposure to this campaign: either it was off everywhere, or it ran everywhere the same way. A twin learns how the holdout moves with the rest of the country; if the campaign ran in only some of them during the history, that relationship is already bent. The plan records which case applies (`design.ads_before_test`), and it changes what the result means:

- **`off` (launch):** the holdout is the campaign's "without" world from day one. The result is what the campaign added.
- **`always_on`:** the holdout markets go dark at `test_start`. The result is what the campaign was adding while it ran. Past advertising keeps working for a while after it stops, so the holdout's sales fall gradually and the measured effect is **conservative** (it understates the campaign). Keep the holdout dark through the cooldown.

### 13.2 Choosing the holdout

The search of §9.2 picks the holdout instead of cells (one market per chosen stratum), so the holdout spans small and large markets. Gates:

- **Holdout share** of national KPI: 10%–20% (default, see §13.6). Markets above half the maximum share can't be held out alone (as in §9.2).
- **At least 10 holdout markets.** A holdout of a handful of markets is noisy, and the twin of a small holdout can lean on one or two markets. In one synthetic state panel, a 6-state holdout drifted 10–15% from its twin within weeks with no effect at all.
- **Balance** (§9.3), holdout vs. campaign markets, on trend, revenue per order, and sales per capita (when population is known). Share and population are left out because the two sides are meant to differ in size. Correlation with the national series is also left out: the campaign markets nearly *are* the nation, so the gap would measure the holdout's noise, which the fit gate already covers.
- **Fit** (§9.3): the holdout twin's forecast error over the last `test_days` of history.

Ranking and power work as in §9.4 and §10, with the lift injected into the campaign markets (§13.5).

### 13.3 The estimator

The obvious design is the wrong one. Building a twin of the *campaign markets* (90% of the country) from the *holdout* (about 10 markets) leaves very few donors, and the twin ends up leaning on one or two of them. We tried it: on 64 synthetic state panels with no effect (holdouts chosen by the planner), its 90% intervals covered zero **80%** of the time and it called a **positive** effect in **16%** of them.

FOSIT instead builds the twin **for the holdout, from the campaign markets**. This has many donors and is the standard setting of §4. To make the campaign markets' movement transfer to the holdout, every series is **indexed** to its own pre-period average:

$$\tilde y_t = \frac{\sum_{i \in H} Y_{it}}{\overline{\sum_{i \in H} Y_{i\cdot}}^{\,\text{pre}}}, \qquad \tilde Y_{jt} = \frac{Y_{jt}}{\overline{Y_{j\cdot}}^{\,\text{pre}}} \quad (j \in \text{campaign markets, screened as in §3})$$

The holdout's index $\tilde y$ is the treated series and the campaign markets' indexes $\tilde Y$ are the donors. Everything in §4–§5 then applies unchanged: ridge ASCM with fixed effects, λ by cross-validation, moving-block conformal inference, intervals by test inversion. On the same 64 panels this covered zero **84%** of the time and called a positive effect in **5%** (the rate a 90% two-sided interval should give).

During the test the campaign markets get the ads and the holdout doesn't, so the twin (built from campaign markets) shows what the holdout would have sold **with** the ads, and the estimated effect $\hat\tau$ (§4.4) is **negative** when the ads work.

### 13.4 From the holdout's gap to business metrics

The **ads share** is the part of with-ads sales the ads were responsible for, over the measurement window $\mathcal W$:

$$d = \frac{\sum_{t \in \mathcal W} (\hat{\tilde y}^{\,N}_t - \tilde y_t)}{\sum_{t \in \mathcal W} \hat{\tilde y}^{\,N}_t} = \frac{-\hat\tau \, |\mathcal W|}{\sum_{t \in \mathcal W} \hat{\tilde y}^{\,N}_t}$$

and the incremental total in the campaign markets is

$$\hat\Delta = d \cdot \sum_{t \in \mathcal W} \sum_{i \in \text{campaign}} Y_{it}.$$

Intervals map through the same formula (it is decreasing in $\tau$, so the upper $\tau$ bound gives the lower $\Delta$ bound). The counterfactual total is observed minus $\hat\Delta$, and lift, iCPA, iROAS and orders per 1,000 follow §6 using the campaign's **actual** spend, so iCPA needs no assumption about money that wasn't spent. Verdicts follow §8.

**Assumptions, stated:**
1. The holdout markets would have responded to the ads like the campaign markets the twin leans on (proportional lift). The twin's weights are listed under "Under the hood".
2. That lift is representative of every campaign market, so it can be applied to all of them. Balance on trend, revenue per order and sales per capita supports this but can't prove it.
3. The holdout received no campaign impressions. The leakage check (§11) counts impressions delivered into holdout markets.

Campaign markets missing from the sales file at read time are dropped from the total and listed (a check warning), rather than stopping the read.

The **chart** shows the holdout: its actual sales and its twin (in the holdout's own sales units). The gap between them is the ads' effect in the holdout's terms.

### 13.5 Power

As in §10, with one change: the lift is injected into the **campaign markets** (the twin's donors) on ads-on days, so the twin rises above the holdout. The twin's weights don't depend on the post-period, so the lifted twin is the pre-period twin plus the weights times the added sales. A design is "detected" when the estimated effect is negative and $p \le \alpha$. MDE and money (§10.2) refer to the campaign markets' sales and the full campaign budget.

### 13.6 Evidence

`tests/test_holdout.py` checks the gates, the translation and the shipped example (`examples/national_holdout`) on every change. `validation/calibration_study.py --design holdout` runs the larger study: 200 synthetic state-level panels (51 states, about 6,500 orders a day nationally, with per-state trends; 18 weeks of history, a 4-week test and 1-week cooldown; holdout chosen by the planner), each read once with no effect and once with lift = the planned MDE. With placebo calibration (§5.6, on by default):

| Holdout share | Covers zero, no effect (90% nominal) | "Positive", no effect (5% nominal) | Covers truth, lift = MDE | "Positive", lift = MDE (80% planned) | Mean bias | Median MDE (4 weeks) |
|---|---|---|---|---|---|---|
| **10%–20% (default)** | **93.0%** | **1.5%** | **97.0%** | **86.5%** | **+0.1%** | **19.4%** |

Before placebo calibration, the same study gave 83% / 7.5% / 95% / 87.5% / −0.6% / 19.4%, and holdout sizes of 5%–15% and 10%–25% gave 80% and 85% coverage of zero (median MDE 20.0% and 19.4%). Larger holdouts calibrate better at about the same sensitivity, which is why the default is 10%–20%.

### 13.7 Several vendors split the country

> **In plain English:** Each vendor runs in its own part of the country, say 40% each, and a group with no CTV at all, say 20%, shows what would have happened without it. Each vendor is measured against that same no-CTV group, using only its own markets.

**Design.** The plan has $K$ cells (2–4 vendors) and a holdout; every market that isn't held out or excluded belongs to exactly one cell. Markets a vendor can't target (`treatment_eligible = false`) get no one's ads, so they are left out of every cell.

**Choosing the split** (`selection.py`). The holdout is drawn as in §13.2 (default 15%–25% of sales; at least 10 markets). The remaining markets are dealt to the cells largest first: each goes to the cell that is smallest so far, measured by the larger of its share of sales and its share of population, so both sales and sales per person stay even; cells within half that market's size of the smallest are equally likely, so the search explores many splits. Each cell must also have at least 10 markets. Balance (§9.3) is checked between the cells (share of sales, trend, revenue per order, sales per person) and between the holdout and all markets with ads (trend, revenue per order, sales per person, as `holdout_*`). A single market that holds a large share of sales at an unusual rate per person can make every split fail the balance gate; then exclude it or accept a looser gate.

**Estimation.** Cell $k$ gets its own twin of the holdout, built only from cell $k$'s markets (§13.3), so cell $k$'s gap is the share of sales *its* ads drove, applied to *its* markets (§13.4). Placebo calibration (§5.6) draws placebo cells from cell $k$'s markets. Power (§10, §13.5) injects the lift into cell $k$'s markets.

**Head-to-head.** Both twins share the holdout as their treated series, so their errors are correlated. The joint conformal region of §7.2 handles this: both cells are permuted with the same time shift. A holdout read maps $\tau$ to incremental sales linearly (§13.4, with a negative slope), so the joint region projects onto every comparison exactly as for geo cells.

**Evidence** (`validation/calibration_study.py --design split`, 200 synthetic state panels, two vendors, placebo calibration on): with no effect, 90% ranges held zero 90.7% of the time and 3.6% were called "positive"; with lift = the planned MDE in vendor 1, ranges held the truth 98.4% of the time and 86% were called positive (80% planned); bias +1.9%; median planned MDE 18.8% for 4 weeks. The head-to-head range held the true difference 99.5% of the time with no effect, and called a difference in 50% of tests where one vendor had its planned MDE and the other none (0.5% with no effect), about the same as the two-cell design (48%).

---

## 14. Known limitations

- **Markets aren't vendors:** head-to-head differences include market differences (§7.3).
- **Spillover:** people who live in one CBSA and shop or watch TV in another blur the line between treatment and control. This usually biases lift toward zero. Not modelled in v1.
- **External validity:** results apply to the tested markets. Scaling to national assumes those markets are representative, which balance checks support but can't prove.
- **Linear budget response:** power-by-budget curves assume no saturation (§10.2).
- **Lift % uncertainty:** treats the counterfactual total as fixed (§6).
- **Short histories:** under 8 weeks of pre-period, fit and power estimates are unreliable. FOSIT warns but doesn't block.
- **Holidays and promotions inside the test window:** fine if they hit treatment and control alike, which the external-shocks check asks about.
- **Out of scope for v1:** household-level holdouts, time-series-only reads without controls (for example, a past campaign that ran nationwide with no market held out), MMM (see README roadmap).
- **National holdout:** the effect is measured in the holdout and applied to the campaign markets, which assumes the ads would have worked the same way there (§13.4).
- **Few markets, wider ranges.** With 51 states, twins drift more than with hundreds of metro areas. Plain conformal ranges were over-confident on such data; placebo calibration (§5.6) corrects that by widening them, so state-level tests need bigger effects to reach a verdict. Prefer metro areas (CBSAs) when vendors can target them.

---

## 15. Defaults reference

| Parameter | Default | Locked in plan |
|---|---|---|
| Geo unit | CBSA | ✓ |
| Aggregation | Daily | ✓ |
| Pre-period | Up to 26 weeks when available. Warn < 8, recommend ≥ 12 (§5.5) | ✓ |
| Cooldown | 7 days | ✓ |
| Fixed effects | On | ✓ |
| λ selection | Time-series CV, 1-SE rule | ✓ |
| Test statistic | Two-sided average effect, $\lvert\sum \hat u\rvert$ (GeoLift's "Total" is $\sum\lvert \hat u\rvert$; see §5.1) | ✓ |
| Permutations | Moving-block (circular shifts). iid optional (§5.5) | ✓ |
| Placebo calibration | 40 placebo cells per cell and KPI; report the hull with the conformal range (§5.6) | ✓ |
| Donor screening | Drop donors with zero KPI on > 50% of pre-period days | ✓ |
| Decision α | 0.10 (90% interval). 95% also reported | ✓ |
| Head-to-head | Joint conformal region, projected | ✓ |
| Cell share of national KPI | 3%–15% | ✓ |
| Min control share | 50% | ✓ |
| Fit gate (holdout nRMSE) | ≤ 10% | ✓ (read threshold = 1.5 × the worse of the achieved holdout fit and the in-sample pre-period fit, capped at 15%) |
| Balance gate | ≤ 10% relative gap | ✓ |
| Power target | 80% | ✓ |
| Leakage warn | > 5% of impressions | ✓ |
| Spend balance warn | ±5 pp share, < 90% of budget | ✓ |
| Candidates searched | 2,000 (seeded) | ✓ (seed) |
| National holdout: holdout share | 10%–20% of national KPI (§13.2) | ✓ (holdout markets) |
| National holdout: min holdout markets | 10 | ✓ (holdout markets) |

---

## 16. References

- Abadie, A., Diamond, A., & Hainmueller, J. (2010). Synthetic control methods for comparative case studies. *JASA* 105(490).
- Ben-Michael, E., Feller, A., & Rothstein, J. (2021). The augmented synthetic control method. *JASA* 116(536).
- Chernozhukov, V., Wüthrich, K., & Zhu, Y. (2021). An exact and robust conformal inference method for counterfactual and synthetic controls. *JASA* 116(536).
- Meta Open Source, GeoLift (R package). Used as the reference implementation for validation only.
- Rundgren, A., Jordan, B., & Erdtman, S. (2020). RFC 8785: JSON Canonicalization Scheme (JCS) (used for plan hashing, see [PREREGISTRATION.md](PREREGISTRATION.md)).
