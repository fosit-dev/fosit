"""Geo crossover: two balanced halves of the country take turns having the ads (METHODOLOGY.md §14).

For advertisers too small for a geo split. The country is split into two halves (A and B) balanced on sales,
population and the shape of sales. The test runs in blocks (default 2 weeks); in every block exactly one half has
the ads, following a random schedule fixed and fingerprinted before launch, with each half on in half the blocks.
National swings hit both halves in the same block and cancel; each half is also compared with itself over time.

Estimate: for every half and block, the log of mean daily sales over the block's days after a washout (the first
days, while the previous block's ads fade). A two-way fixed-effects fit (half + block) gives the log lift tau of
the ads. Inference is exact: the sharp null "the ads change log sales by tau0" is tested against every other
balanced schedule the randomization could have produced (Fisher; Bojinov, Simchi-Levi & Zhao 2023), and the
range is every tau0 not rejected. No modelling assumption about how sales move over time is needed.

Incremental sales: the ads' total effect over time equals the steady lift times the ads-on days, whatever their
build-up and fade (an adstock's mass is conserved), so incremental = (1 - e^-tau) x sales in the ads-on blocks.
tau is measured after the washout, close to the steady state; if effects build slowly it is understated (cautious).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from itertools import combinations

import numpy as np
import pandas as pd

from .panel import Panel

BLOCK_DAYS = (7, 14, 28)
WASHOUT = {7: 2, 14: 3, 28: 5}          # days dropped at the start of every block
MAX_SCHEDULES = 5000                     # exact randomization up to this many balanced schedules, else a seeded sample
COARSE_EFFECTS = (0.025, 0.05, 0.10, 0.15, 0.20, 0.30, 0.50)
# Planning assumes the ads' effect builds up and fades with this half-life (days), so the simulated lift is the one the
# washed-out block days would really show (§14.4). Longer-lasting effects make the real test less sensitive.
PLANNING_HALF_LIFE = 3.0


def adstock(on_daily: np.ndarray, half_life: float) -> np.ndarray:
    """Share of the full effect present each day, for ads switched on and off as `on_daily` (0/1) says."""
    k = 0.5 ** (1 / half_life)
    out, acc = np.zeros(len(on_daily)), 0.0
    for t, x in enumerate(on_daily):
        acc = acc * k + x * (1 - k)
        out[t] = acc
    return out


# ---------------------------------------------------------------------------- the design's arithmetic

def schedules(n_blocks: int, n_on: int | None = None, seed: int = 0) -> np.ndarray:
    """Every schedule with half A on in `n_on` of `n_blocks` blocks (default half), as 0/1 rows (1 = A has the ads)."""
    n_on = n_blocks // 2 if n_on is None else n_on
    n_all = math.comb(n_blocks, n_on)
    if n_all <= MAX_SCHEDULES:
        rows = [np.isin(np.arange(n_blocks), c).astype(float) for c in combinations(range(n_blocks), n_on)]
        return np.array(rows)
    rng = np.random.default_rng(seed)
    out = np.zeros((MAX_SCHEDULES, n_blocks))
    for i in range(MAX_SCHEDULES):
        out[i, rng.choice(n_blocks, n_on, replace=False)] = 1
    return out


def block_means(mat_a: np.ndarray, mat_b: np.ndarray, start: int, block_days: int, n_blocks: int, washout: int) -> np.ndarray:
    """(2, n_blocks) mean daily sales per half per block, over each block's days after the washout."""
    out = np.zeros((2, n_blocks))
    for b in range(n_blocks):
        days = slice(start + b * block_days + washout, start + (b + 1) * block_days)
        out[0, b] = mat_a[days].mean()
        out[1, b] = mat_b[days].mean()
    return out


def log_ratio(means: np.ndarray) -> np.ndarray:
    """Per block, log(A) - log(B): the only thing the two-way fit uses with two halves."""
    m = np.maximum(means, 0.5 / 7)          # a block with no sales at all can't be logged; treat as half an order a week
    return np.log(m[0]) - np.log(m[1])


def estimate_tau(d: np.ndarray, a_on: np.ndarray) -> float:
    """Two-way fixed effects with two halves: tau = mean of d where A is on minus where B is on, halved."""
    return float((d[a_on == 1].mean() - d[a_on == 0].mean()) / 2)


def p_value(d: np.ndarray, a_on: np.ndarray, tau0: float, scheds: np.ndarray) -> float:
    """Fisher randomization p-value for the sharp null 'the ads change log sales by tau0' (§14.3)."""
    # Under the null, remove the effect where it happened: A-on blocks lose tau0 in A, B-on blocks lose tau0 in B.
    base = d - tau0 * (2 * a_on - 1)
    obs = abs(estimate_tau(base, a_on))
    stats = np.abs((base @ scheds.T / scheds.sum(1) - base @ (1 - scheds).T / (1 - scheds).sum(1)) / 2)
    return float(np.mean(stats >= obs - 1e-12))


def interval(d: np.ndarray, a_on: np.ndarray, scheds: np.ndarray, level: float) -> tuple[float, float]:
    """Every tau0 the randomization test doesn't reject at 1 - level (bisection out from the estimate)."""
    alpha = round(1 - level, 12)
    est = estimate_tau(d, a_on)
    spread = float(np.std(d)) or 0.05
    bounds = []
    for direction in (-1, 1):
        inside, step = est, spread
        outside = None
        for _ in range(30):
            cand = est + direction * step
            if p_value(d, a_on, cand, scheds) <= alpha:
                outside = cand
                break
            inside, step = cand, step * 2
        if outside is None:
            bounds.append(direction * math.inf)
            continue
        for _ in range(40):
            mid = (inside + outside) / 2
            if p_value(d, a_on, mid, scheds) > alpha:
                inside = mid
            else:
                outside = mid
            if abs(outside - inside) < 1e-4:
                break
        bounds.append(inside)
    return bounds[0], bounds[1]


def noise(d: np.ndarray) -> float:
    """How much the halves' ratio wanders from block to block (SD of log(A/B)): the yardstick for planning and the check."""
    return float(np.std(d - d.mean(), ddof=1)) if len(d) > 1 else math.inf


# ---------------------------------------------------------------------------- planning (§14.2)

@dataclass
class CrossoverConfig:
    kpi: str = "orders"
    block_days: int = 14
    n_blocks: tuple = (8, 12)               # test lengths to compare, in blocks
    alpha: float = 0.10
    power_target: float = 0.80
    # The replay is one stretch of history, so its sensitivity estimate is noisy and, on average, flattering. Planning
    # aims this much higher in the replay so real tests reach power_target (§14.4: 80% planned, 82% achieved).
    replay_margin: float = 0.10
    # How fast the ads' effect builds up and fades, in days (§14.4): 3 for most performance CTV (2-week blocks);
    # 7 for advertising that keeps working a week or more (4-week blocks).
    half_life: float = PLANNING_HALF_LIFE
    balance_max: float = 0.10
    n_candidates: int = 600
    shortlist: int = 20
    power_designs: int = 5
    schedules_per_window: int = 30
    seed: int = 0
    excluded: set = field(default_factory=set)
    not_eligible: set = field(default_factory=set)
    population: dict | None = None

    @property
    def washout(self) -> int:
        return WASHOUT.get(self.block_days, max(1, self.block_days // 5))


def _relative_gap(a: float, b: float) -> float:
    m = (abs(a) + abs(b)) / 2
    return abs(a - b) / m if m > 0 else 0.0


def find_halves(panel: Panel, cfg: CrossoverConfig, budget: float = 0.0, progress=None) -> dict:
    """Balanced halves ranked by how small a lift the crossover could detect on this history."""
    from .power import calibration_flag

    if cfg.kpi not in panel.kpis:
        raise ValueError(f"KPI {cfg.kpi!r} not in data")
    Y = panel.kpis[cfg.kpi]
    usable = np.array([g not in cfg.excluded and g not in cfg.not_eligible for g in panel.geos])
    rows = np.nonzero(usable)[0]
    if len(rows) < 4:
        raise ValueError("A crossover needs at least 4 markets.")
    share = Y.sum(axis=1) / max(Y[rows].sum(), 1e-9)
    pop = None
    if cfg.population:
        pop = np.array([float(cfg.population.get(g, np.nan)) for g in panel.geos])
        if np.isnan(pop[rows]).any():
            pop = None
    rev = panel.kpis.get("revenue") if cfg.kpi == "orders" else None
    orders = panel.kpis.get("orders")
    rng = np.random.default_rng(cfg.seed)
    order = rows[np.argsort(-share[rows], kind="stable")]
    hist_blocks = panel.n_days // cfg.block_days

    def features(r):
        agg = Y[r].sum(axis=0)
        f = {"share": float(share[r].sum())}
        q = min(28, panel.n_days // 2)
        first, last = agg[:q].sum(), agg[-q:].sum()
        f["trend"] = float(last / first) if first > 0 else math.nan
        if pop is not None:
            f["per_capita"] = float(Y[r].sum() / pop[r].sum())
        if rev is not None and orders is not None and orders[r].sum() > 0:
            f["aov"] = float(rev[r].sum() / orders[r].sum())
        return f

    seen, cands = set(), []
    for _ in range(cfg.n_candidates * 3):
        if len(cands) >= cfg.n_candidates:
            break
        sales, people, halves = np.zeros(2), np.zeros(2), [[], []]
        scale = pop[order].sum() / max(share[order].sum(), 1e-9) if pop is not None else None
        for g in order:   # largest first, to the smaller half; near-ties at random (as for the vendor split, §13.7)
            size = max(share[g], pop[g] / scale) if pop is not None else share[g]
            load = np.maximum(sales, people) if pop is not None else sales
            h = int(rng.choice(np.nonzero(load <= load.min() + 0.5 * size)[0]))
            halves[h].append(g)
            sales[h] += share[g]
            if pop is not None:
                people[h] += pop[g] / scale
        a, b = np.array(sorted(halves[0])), np.array(sorted(halves[1]))
        key = tuple(a)
        if key in seen or len(a) < 2 or len(b) < 2:
            continue
        seen.add(key)
        fa, fb = features(a), features(b)
        balance = {k: _relative_gap(fa[k], fb[k]) for k in fa if k in fb and not math.isnan(fa[k]) and not math.isnan(fb[k])}
        if max(balance.values()) > cfg.balance_max:
            continue
        ya, yb = Y[a].sum(axis=0), Y[b].sum(axis=0)
        d = log_ratio(block_means(ya, yb, panel.n_days - hist_blocks * cfg.block_days, cfg.block_days, hist_blocks, cfg.washout))
        cands.append({"a": a, "b": b, "balance": balance, "noise": noise(d), "ya": ya, "yb": yb})
    funnel = {"generated": len(seen), "passed_share_and_balance": len(cands)}
    # Rank by balance, not by how well the halves happened to track each other in the past: picking the luckiest history
    # would make the replayed sensitivity look better than the real test will be (§14.4).
    cands.sort(key=lambda x: (max(x["balance"].values()), x["noise"]))
    top = cands[: cfg.shortlist]
    funnel["passed_fit"] = len(top)
    designs = []
    for i, c in enumerate(top):
        design = {"cells": [[panel.geos[r] for r in c["a"]]], "control": [panel.geos[r] for r in c["b"]],
                  "shares": [float(share[c["a"]].sum())], "control_share": float(share[c["b"]].sum()),
                  "balance": c["balance"], "balance_score": max(c["balance"].values()), "fit": [c["noise"]],
                  "fit_screen": [c["noise"]], "pre_fit": [c["noise"]], "share_in_test": 1.0, "power": None}
        if i < cfg.power_designs:
            curves = [simulate_power(c["ya"], c["yb"], cfg, nb, budget) for nb in cfg.n_blocks]
            design["power"] = {"cells": [{"cell_index": 0, "curves": curves}]}
            if progress:
                progress({"stage": "power", "done": i + 1, "total": min(cfg.power_designs, len(top)), "design": i + 1,
                          "designs": min(cfg.power_designs, len(top))})
        designs.append(design)

    # Designs stay in balance order: re-ranking them by replayed sensitivity would favour lucky histories again.
    return {"designs": designs, "funnel": funnel, "best_failing": [], "fit_period": "block",
            "settings": {"crossover": {k: (sorted(v) if isinstance(v, set) else v) for k, v in vars(cfg).items()
                                       if k not in ("population", "excluded", "not_eligible")}}}


def simulate_power(ya: np.ndarray, yb: np.ndarray, cfg: CrossoverConfig, n_blocks: int, budget: float) -> dict:
    """Replay the crossover on past windows of the history with random schedules and a known lift (§14.4)."""
    from .power import calibration_flag

    L = cfg.block_days
    span = n_blocks * L
    starts = list(range(len(ya) - span, -1, -7))[:10]
    rng = np.random.default_rng(cfg.seed + n_blocks)
    scheds = schedules(n_blocks, seed=cfg.seed)
    test_days = span
    if not starts:
        return {"test_days": test_days, "windows": 0, "points": [], "mde": None, "false_positive_rate": None,
                "calibration_flag": False, "baseline_daily": None, "baseline_test_total": None,
                "note": "History too short to replay a test this long.", "money": {}}
    trials = []
    for s in starts:
        wa, wb = ya[s:s + span], yb[s:s + span]
        for _ in range(cfg.schedules_per_window):
            a_on = scheds[rng.integers(len(scheds))]
            on_a = np.repeat(a_on, L)
            trials.append((wa, wb, a_on, adstock(on_a, cfg.half_life), adstock(1 - on_a, cfg.half_life)))

    def power(effect):
        hits = 0
        for wa, wb, a_on, sa, sb in trials:   # each half gets the lift while (and shortly after) it has the ads
            dd = log_ratio(block_means(wa * (1 + effect * sa), wb * (1 + effect * sb), 0, L, n_blocks, cfg.washout))
            if effect > 0 and estimate_tau(dd, a_on) <= 0:
                continue
            hits += p_value(dd, a_on, 0.0, scheds) <= cfg.alpha
        return hits / len(trials)

    target = min(0.95, cfg.power_target + cfg.replay_margin)
    points = {0.0: power(0.0)}
    crossing = None
    for e in COARSE_EFFECTS:
        points[e] = power(e)
        if points[e] >= target:
            crossing = e
            break
    mde = None
    if crossing is not None:
        lo, hi = max(k for k in points if k < crossing), crossing
        for _ in range(3):
            mid = round((lo + hi) / 2, 4)
            points[mid] = power(mid)
            lo, hi = (mid, hi) if points[mid] < target else (lo, mid)
        mde = hi
    # baseline: sales in the ads-on half-blocks over a test this long (half the country, half the time... on average
    # each day one half has the ads, so the ads-on sales are about half of all sales)
    recent = (ya[-28:].mean() + yb[-28:].mean())
    baseline_test_total = float(recent * span / 2)
    curve = {"test_days": test_days, "windows": len(starts), "points": [{"effect": k, "power": v} for k, v in sorted(points.items())],
             "mde": mde, "false_positive_rate": points[0.0],
             "calibration_flag": calibration_flag(round(points[0.0] * len(trials)), len(trials), cfg.alpha),
             "baseline_daily": float(recent), "baseline_test_total": baseline_test_total, "pre_days": len(ya),
             "note": "" if mde is not None else f"Above {COARSE_EFFECTS[-1]:.0%}: not detectable with this design."}
    units = mde * baseline_test_total if mde else None
    curve["money"] = {"mde_units": units, "detectable_icpa": budget / units if units and budget and cfg.kpi == "orders" else None,
                      "detectable_iroas": units / budget if units and budget and cfg.kpi == "revenue" else None}
    return curve


def random_schedule(n_blocks: int, rng=None) -> str:
    """A fair random schedule, each half on in exactly half the blocks: 'A' or 'B' per block."""
    import secrets
    order = list(range(n_blocks))
    for i in range(n_blocks - 1, 0, -1):   # Fisher-Yates with a cryptographic coin (the plan locks the result)
        j = secrets.randbelow(i + 1) if rng is None else int(rng.integers(i + 1))
        order[i], order[j] = order[j], order[i]
    a_on = set(order[: n_blocks // 2])
    return "".join("A" if b in a_on else "B" for b in range(n_blocks))


# ---------------------------------------------------------------------------- reading (§14.3)

@dataclass
class CrossoverEstimate:
    """A crossover read for one KPI, with the interface the Read module uses for a cell."""

    kpi: str
    tau: float
    p_value: float
    tau_intervals: dict          # level -> (lo, hi) in log lift
    on_sales: float              # sales in the ads-on half-blocks (all days)
    pre_noise: float             # noise() over the pre-period blocks
    block_table: list
    dates: pd.DatetimeIndex
    observed_daily: np.ndarray   # both halves together
    on_daily: np.ndarray         # the ads-on half's daily sales (0 outside the test)
    n_pre: int
    test_days: int
    schedules_tested: int

    att = property(lambda s: s.tau)
    pre_fit_nrmse = property(lambda s: s.pre_noise)

    def _inc(self, tau: float) -> float:
        return (1 - math.exp(-tau)) * self.on_sales if math.isfinite(tau) else (math.inf if tau > 0 else -math.inf)

    @property
    def incremental(self) -> float:
        return self._inc(self.tau)

    def incremental_interval(self, level: float) -> tuple[float, float]:
        lo, hi = self.tau_intervals[level]
        return self._inc(lo), self._inc(hi)

    @property
    def observed_total(self) -> float:
        return self.on_sales

    @property
    def counterfactual_total(self) -> float:
        return self.on_sales - self.incremental

    @property
    def lift(self) -> float:
        return math.expm1(self.tau)

    def test_counterfactual(self, test_days: int) -> float:
        return self.counterfactual_total

    def chart(self) -> dict:
        cf = self.observed_daily - self.on_daily * (1 - math.exp(-self.tau))
        return {"observed": self.observed_daily.round(2).tolist(), "counterfactual": cf.round(2).tolist(), "role": "crossover"}


def estimate_crossover(panel: Panel, kpi: str, half_a, half_b, c: dict, levels, end: pd.Timestamp) -> CrossoverEstimate:
    d_ = c["dates"]
    design = c["design"]
    L, W = int(design["block_days"]), int(design["washout_days"])
    schedule = design["schedule"]
    start = panel.day(d_["test_start"])
    complete = min(len(schedule), (panel.day(end) - start + 1) // L)
    if complete < 2:
        raise ValueError("At least two complete blocks are needed to read a crossover.")
    schedule = schedule[:complete]
    a_on = np.array([1.0 if x == "A" else 0.0 for x in schedule])
    if a_on.min() == a_on.max():
        raise ValueError("The blocks read so far all had the ads in the same half; wait for the next block.")
    mat = panel.kpis[kpi]
    ya, yb = mat[panel.rows(half_a)].sum(axis=0), mat[panel.rows(half_b)].sum(axis=0)
    means = block_means(ya, yb, start, L, complete, W)
    dvec = log_ratio(means)
    scheds = schedules(complete, int(a_on.sum()), seed=int(c["method"].get("seed", 0)))
    tau = estimate_tau(dvec, a_on)
    p0 = p_value(dvec, a_on, 0.0, scheds)
    ints = {lv: interval(dvec, a_on, scheds, lv) for lv in levels}
    on_daily = np.zeros(panel.n_days)
    blocks = []
    for b in range(complete):
        days = slice(start + b * L, start + (b + 1) * L)
        on_daily[days] = (ya if a_on[b] else yb)[days]
        blocks.append({"start": panel.dates[start + b * L].strftime("%Y-%m-%d"), "on": schedule[b],
                       "a_daily": float(means[0, b]), "b_daily": float(means[1, b])})
    pre_start, pre_end = panel.day(d_["pre_start"]), panel.day(d_["pre_end"])
    n_pre_blocks = (pre_end - pre_start + 1) // L
    pre_d = log_ratio(block_means(ya, yb, pre_end + 1 - n_pre_blocks * L, L, n_pre_blocks, W)) if n_pre_blocks >= 2 else np.array([])
    view = slice(max(0, start - 56), start + complete * L)
    return CrossoverEstimate(
        kpi=kpi, tau=tau, p_value=p0, tau_intervals=ints, on_sales=float(on_daily.sum()),
        pre_noise=noise(pre_d) if len(pre_d) > 1 else math.nan, block_table=blocks, dates=panel.dates[view],
        observed_daily=(ya + yb)[view], on_daily=on_daily[view], n_pre=start - view.start, test_days=complete * L,
        schedules_tested=len(scheds))


def leakage(spend, half_a: set, half_b: set, schedule: str, test_start: str, block_days: int) -> dict:
    """Impressions delivered to the half that should have been dark on that day (§14.3), and unattributable ones."""
    rows = spend.rows
    total = float(rows["impressions"].sum())
    if total <= 0:
        return {"impressions": 0.0, "leak_share": 0.0, "unverifiable_share": 0.0, "share": {}}
    block = ((rows["date"] - pd.Timestamp(test_start)).dt.days // block_days).clip(lower=0)
    on_half = block.map(lambda b: schedule[int(b)] if int(b) < len(schedule) else "-")
    dark = ((on_half == "A") & rows["geo_id"].isin(half_b)) | ((on_half == "B") & rows["geo_id"].isin(half_a))
    unknown = rows["geo_id"] == "*"
    return {"impressions": total, "leak_share": float(rows.loc[dark, "impressions"].sum() / total),
            "unverifiable_share": float(rows.loc[unknown, "impressions"].sum() / total),
            "share": {"dark_half": float(rows.loc[dark, "impressions"].sum() / total)}}


def run_read_crossover(panel: Panel, c: dict, spend, today: str, plan_hash: str = "") -> dict:
    """The Read module for a crossover plan: same result shape as a geo read (one cell, no head-to-head)."""
    from .read import _clean, business_metrics, results_csv, verdict

    d = c["dates"]
    method = c["method"]
    alpha = float(method["alpha"])
    levels = tuple(sorted(set(float(x) for x in method.get("report_levels", [0.9, 0.95])) | {round(1 - alpha, 12)}))
    decision_level = round(1 - alpha, 12)
    design = c["design"]
    cell = c["cells"][0]
    present = set(panel.geos)
    half_a = [g for g in cell["geo_ids"] if g in present]
    half_b = [g for g in c["control"]["geo_ids"] if g in present]
    first, last = panel.dates[0], panel.dates[-1]
    errors = []
    if pd.Timestamp(d["pre_start"]) < first:
        errors.append(f"The sales file must start by {d['pre_start']} (the plan's history period); it starts {first:%Y-%m-%d}.")
    if pd.Timestamp(d["test_start"]) > last:
        errors.append(f"The sales file ends {last:%Y-%m-%d}, before the test started on {d['test_start']}.")
    if not half_a or not half_b:
        errors.append("Both halves need markets with sales rows.")
    if errors:
        return {"ok": False, "errors": errors}
    end = min(pd.Timestamp(d["test_end"]), last)
    interim = end < pd.Timestamp(d["test_end"]) or pd.Timestamp(today) < pd.Timestamp(d["test_end"])
    kpis = [k for k in [c["kpi"]["primary"], *c["kpi"].get("secondary", [])] if k in panel.kpis]
    spend_total = spend.spend_by_cell().get(cell["id"]) if spend else None
    kpi_out, ests = {}, {}
    try:
        for kpi in kpis:
            ests[kpi] = estimate_crossover(panel, kpi, half_a, half_b, c, levels, end)
    except ValueError as e:
        return {"ok": False, "errors": [str(e)]}
    thresholds = c["thresholds"]
    for kpi, est in ests.items():
        m = business_metrics(est, kpi, spend_total, levels)
        limit = thresholds["pre_fit_nrmse_max"].get(cell["id"], {}).get(kpi)
        m["pre_fit_period"] = "block"
        m["pre_fit_limit"] = limit
        m["pre_fit_ok"] = True if limit is None or not math.isfinite(est.pre_noise) else est.pre_noise <= limit
        m["series"] = {"dates": [x.strftime("%Y-%m-%d") for x in est.dates], **est.chart(), "n_pre": est.n_pre,
                       "test_days": est.test_days}
        m["placebo"] = None
        m["under_the_hood"] = {"blocks": est.block_table, "schedules_tested": est.schedules_tested,
                               "block_days": design["block_days"], "washout_days": design["washout_days"],
                               "lambda": None, "top_weights": [], "negative_weight_sum": 0.0, "donors": len(half_b),
                               "dropped_donors": [], "tests_evaluated": est.schedules_tested}
        kpi_out[kpi] = m
    primary = c["kpi"]["primary"]
    pest = ests[primary]
    dec = c["decision"]
    meaningful, basis = None, ""
    if dec["meaningful_effect_basis"] == "target_icpa" and primary == "orders" and dec.get("target_icpa") and spend_total:
        meaningful, basis = spend_total / float(dec["target_icpa"]), f"orders needed to reach the target iCPA of {dec['target_icpa']}"
    elif dec["meaningful_effect_basis"] == "breakeven_iroas" and primary == "revenue" and dec.get("breakeven_iroas") and spend_total:
        meaningful, basis = spend_total * float(dec["breakeven_iroas"]), f"revenue needed to reach the break-even iROAS of {dec['breakeven_iroas']}"
    elif (dec.get("planned_mde_lift") or {}).get(cell["id"]):
        mde = float(dec["planned_mde_lift"][cell["id"]])
        meaningful, basis = mde * pest.counterfactual_total, f"the planned minimum detectable lift of {mde:.1%}"
    v, why = verdict(pest, decision_level, meaningful, True)   # the randomization test is exact: noisy halves only widen it
    leak = leakage(spend, set(half_a), set(half_b), design["schedule"], d["test_start"], int(design["block_days"])) if spend else None
    cells_out = [{"id": cell["id"], "label": cell["label"], "budget": float(cell["budget"]), "spend": spend_total,
                  "n_geos": len(half_a) + len(half_b), "kpis": kpi_out, "verdict": v, "verdict_reason": why,
                  "meaningful_effect": meaningful, "meaningful_basis": basis,
                  "fit_checks": [{"kpi": k, "nrmse": e.pre_noise, "limit": kpi_out[k]["pre_fit_limit"], "ok": kpi_out[k]["pre_fit_ok"],
                                  "period": "block"} for k, e in ests.items()],
                  "leakage": leak}]
    checks = _checks(c, cells_out, spend, interim, end, pest, thresholds)
    result = {"ok": True, "interim": interim, "design": "crossover",
              "window": {"pre_start": d["pre_start"], "pre_end": d["pre_end"], "start": d["test_start"],
                         "end": end.strftime("%Y-%m-%d"), "planned_end": d["test_end"], "days": pest.test_days,
                         "test_days": pest.test_days},
              "alpha": alpha, "decision_level": decision_level, "levels": list(levels),
              "permutations": {"kind": "randomization", "n": pest.schedules_tested},
              "primary_kpi": primary, "primary_metric": dec["primary_metric"], "cells": cells_out, "head_to_head": [],
              "checks": checks}
    result["csv"] = results_csv(result, plan_hash)
    return _clean(result)


def _checks(c, cells_out, spend, interim, end, pest, th) -> list[dict]:
    cell = cells_out[0]
    out = []
    bad = [f for f in cell["fit_checks"] if not f["ok"]]
    out.append({"id": "pre_fit", "title": "Halves tracked each other", "status": "warn" if bad else "pass", "blocking": False,
                "detail": ("Before the test, the halves' ratio wandered more than the plan expected "
                           + "; ".join(f"({f['kpi']}: {f['nrmse']:.1%} > {f['limit']:.1%})" for f in bad)
                           + ". The ranges already account for it (the test is exact), so they are wider rather than wrong.")
                if bad else "Before the test, the two halves moved together as closely as the plan expected."})
    if spend is None:
        out.append({"id": "leakage", "title": "Schedule followed", "status": "warn", "blocking": False,
                    "detail": "No spend & delivery file loaded, so we can't check the ads followed the schedule."})
        out.append({"id": "spend_balance", "title": "Spend", "status": "warn", "blocking": False,
                    "detail": "No spend & delivery file loaded: iCPA and iROAS can't be computed."})
    else:
        l = cell["leakage"]
        warn = float(th["leakage_warn_share"])
        bad_leak = l and (l["leak_share"] > warn or l["unverifiable_share"] > warn)
        out.append({"id": "leakage", "title": "Schedule followed", "status": "warn" if bad_leak else "pass", "blocking": False,
                    "detail": (f"{l['leak_share']:.1%} of impressions ran in the half that should have been dark, "
                               f"{l['unverifiable_share']:.1%} couldn't be placed. That pushes the measured lift toward zero.")
                    if bad_leak else f"At most {warn:.0%} of impressions ran in the dark half or couldn't be placed."})
        s = cell["spend"] or 0
        low = s < float(th["min_budget_delivery"]) * cell["budget"]
        out.append({"id": "spend_balance", "title": "Spend", "status": "warn" if low else "pass", "blocking": False,
                    "detail": f"Spent {s:,.0f} of the {cell['budget']:,.0f} budget." + (" iCPA uses actual spend, so it stays correct." if low else "")})
    out.append({"id": "timing", "title": "Timing", "status": "warn" if interim else "pass", "blocking": False,
                "detail": (f"Read before the last block ended ({c['dates']['test_end']}): data covers whole blocks to "
                           f"{end:%Y-%m-%d}. This is an INTERIM result.") if interim else "Read after the last block ended."})
    return out
