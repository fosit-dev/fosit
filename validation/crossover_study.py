"""Crossover study (METHODOLOGY.md §14.5): is the geo crossover honest and as sensitive as planned for small advertisers?

    python validation/crossover_study.py [--orders-per-day 100] [--seeds 200] [--half-life 3] [--block-days 14] [--blocks 8]
                                         [--planning-half-life H] [--workers 4]

For each seed: synthetic daily orders for the 50 states + DC (core/fosit/synthetic.py) at the given national volume,
26 weeks of history, then the test period. Plan exactly as the app does (api.find_designs, design crossover, with the
planning half-life the app uses for this block length), draw a random schedule, and read the test twice: with no effect,
and with the planned minimum detectable lift added to whichever half has the ads, building up and fading with the TRUE
half-life `--half-life` (days). Set `--half-life` above the planning half-life to see a wrong answer to "how long do the
ads keep working?" (§14.5). Everything is seeded.

Two truths are reported. "Test window": extra orders inside the test (what earlier versions of this study used).
"All extra orders": the test window plus the expected extra orders after the test ends, while the last block's ads
fade. The Read module's estimate, (1 - e^-tau) x ads-on sales, claims the second one (§14.3).
"""

import argparse
import math
import os
import platform
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "core"))
from fosit import api, crossover, synthetic  # noqa: E402
from fosit.panel import load_kpi_history  # noqa: E402
from fosit.read import run_read  # noqa: E402

HISTORY, TEST_START = 182, "2027-01-04"
# The planning half-life the web app and the skill CLI lock for each block length ("a few days" -> 2-week blocks,
# "a week or more" -> 4-week blocks; web/src/plan/state.ts crossoverSetup, fosit_cli.py _design_cfg).
APP_PLANNING_HALF_LIFE = {14: 3.0, 28: 7.0}


def planning_half_life(block_days: int) -> float:
    return APP_PLANNING_HALF_LIFE.get(block_days, crossover.PLANNING_HALF_LIFE)


def schedule_rng(seed: int) -> np.random.Generator:
    """The schedule's own random stream. Reusing the planning seed made the schedule depend on how the halves were
    drawn, which a real (cryptographic) draw never does; with 6 blocks it inflated 'positive' with no effect to 9%."""
    return np.random.default_rng([seed, 2])


def fade_after_test(orders_half: np.ndarray, share_end: float, lift: float, half_life: float) -> float:
    """Expected extra orders after the test ends, while the last block's ads keep fading (geometric adstock)."""
    k = 0.5 ** (1 / half_life)
    base = float(orders_half[-14:].sum()) / 14 if len(orders_half) else 0.0
    return lift * base * share_end * k / (1 - k)


def one_seed(args) -> list[dict]:
    seed, per_day, half_life, L, B, plan_h = args
    t0 = time.perf_counter()
    attrs = api.geo_attributes("state")
    per_100k = per_day / (sum(a["population"] for a in attrs) / 1e5)
    days = HISTORY + L * B
    start = (pd.Timestamp(TEST_START) - pd.Timedelta(days=HISTORY)).strftime("%Y-%m-%d")
    end = (pd.Timestamp(start) + pd.Timedelta(days=days - 1)).strftime("%Y-%m-%d")
    df = synthetic.sample_state_history(attrs, end, n_days=days, seed=300 + seed, orders_per_100k=per_100k)
    api.load_history(df[df.date < TEST_START].to_csv(index=False), "state")
    found = api.find_designs({"design": "crossover", "block_days": L, "durations": [L * B], "seed": seed, "budgets": [50000],
                              "power_designs": 3, "half_life": plan_h})
    if not found["designs"]:
        return [{"failed": "no_design", "seconds": time.perf_counter() - t0}]
    d = found["designs"][0]
    mde = d["power"]["cells"][0]["curves"][0]["mde"]      # None: the planner could not size this test (reported, not replaced)
    schedule = crossover.random_schedule(B, schedule_rng(seed))
    test_end = (pd.Timestamp(TEST_START) + pd.Timedelta(days=L * B - 1)).strftime("%Y-%m-%d")
    c = {"dates": {"pre_start": start, "pre_end": (pd.Timestamp(TEST_START) - pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                   "test_start": TEST_START, "test_end": test_end, "cooldown_end": test_end},
         "design": {"type": "crossover", "block_days": L, "washout_days": crossover.WASHOUT[L], "schedule": schedule,
                    "planning_half_life": plan_h},
         "cells": [{"id": "cell_1", "label": "Campaign", "geo_ids": d["cells"][0], "budget": 50000}],
         "control": {"geo_ids": d["control"]}, "excluded": {"geo_ids": []}, "kpi": {"primary": "orders", "secondary": []},
         "method": {"alpha": 0.1, "report_levels": [0.9], "seed": seed},
         "thresholds": {"pre_fit_nrmse_max": {}, "leakage_warn_share": 0.05, "spend_share_tolerance_pp": 5,
                        "min_budget_delivery": 0.9, "power_target": 0.8},
         "decision": {"primary_metric": "cell_lift", "meaningful_effect_basis": "planned_mde",
                      "planned_mde_lift": {"cell_1": mde if mde else 0.0}}}
    out = []
    test = (df.date >= TEST_START).to_numpy()
    day = (pd.to_datetime(df.date) - pd.Timestamp(TEST_START)).dt.days.to_numpy()
    on_a = np.repeat([1.0 if x == "A" else 0.0 for x in schedule], L)
    for lift in ((0.0, mde) if mde else (0.0,)):
        extra = np.zeros(len(df))
        fade = 0.0
        if lift:
            rng = np.random.default_rng([seed, 7])
            for half, on in ((set(d["cells"][0]), on_a), (set(d["control"]), 1 - on_a)):
                share = crossover.adstock(on, half_life)
                m = test & df.geo_id.isin(half).to_numpy()
                lam = df.loc[m, "orders"].to_numpy() * lift * share[day[m]]
                extra[m] = rng.poisson(lam)
                daily = df.loc[m].groupby("date").orders.sum().to_numpy()
                fade += fade_after_test(daily, float(share[-1]), lift, half_life)
        full = df.copy()
        full["orders"] = full["orders"] + extra
        panel, _ = load_kpi_history(full.to_csv(index=False))
        cell = run_read(panel, c, None, "2027-12-31")["cells"][0]
        m = cell["kpis"]["orders"]
        lo, hi = m["intervals"]["0.9"]["incremental"]
        window = float(extra.sum())
        out.append({"lift": lift, "mde": mde, "truth_window": window, "truth_all": window + fade, "estimate": m["incremental"],
                    "lo": lo, "hi": hi, "verdict": cell["verdict"]})
    out[-1]["seconds"] = time.perf_counter() - t0
    if not mde:
        out[-1]["failed"] = "no_mde"
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--orders-per-day", type=float, default=100)
    p.add_argument("--seeds", type=int, default=200)
    p.add_argument("--half-life", type=float, default=3.0, help="TRUE half-life of the ads' effect, in days")
    p.add_argument("--block-days", type=int, default=14)
    p.add_argument("--blocks", type=int, default=8)
    p.add_argument("--planning-half-life", type=float,
                   help="half-life the planner assumes (default: what the app locks for this block length)")
    p.add_argument("--workers", type=int, default=4)
    a = p.parse_args()
    plan_h = a.planning_half_life or planning_half_life(a.block_days)
    t0 = time.perf_counter()
    with ProcessPoolExecutor(a.workers) as pool:
        rows = [r for rs in pool.map(one_seed, [(s, a.orders_per_day, a.half_life, a.block_days, a.blocks, plan_h)
                                                 for s in range(a.seeds)]) for r in rs]
    wall = time.perf_counter() - t0
    no_design = sum(1 for x in rows if x.get("failed") == "no_design")
    no_mde = sum(1 for x in rows if x.get("failed") == "no_mde")
    r = pd.DataFrame([x for x in rows if "verdict" in x])
    null, lift = r[r.lift == 0], r[r.lift > 0]
    print(f"crossover, {a.orders_per_day:.0f} orders/day, {a.blocks} blocks x {a.block_days} days "
          f"(washout {crossover.WASHOUT[a.block_days]}), true effect half-life {a.half_life:g} days, "
          f"planning half-life {plan_h:g} days, {a.seeds} seeds")
    secs = [x["seconds"] for x in rows if "seconds" in x]
    print(f"  python {platform.python_version()}, numpy {np.__version__}, pandas {pd.__version__}; "
          f"{wall:.0f} s wall on {a.workers} workers, {np.mean(secs):.1f} s per seed (plan + reads)")
    print(f"  seeds with no balanced design:        {no_design}")
    print(f"  seeds the planner could not size:     {no_mde}  (no lift read for these)")
    print(f"  no effect: range covers zero:         {((null.lo <= 0) & (null.hi >= 0)).mean():.1%}  (90% nominal)")
    print(f"  no effect: 'positive':                {(null.verdict == 'positive').mean():.1%}  (5% expected)")
    if len(lift):
        all_, win = lift.truth_all, lift.truth_window
        print(f"  lift = MDE: 'positive':               {(lift.verdict == 'positive').mean():.1%}  (plan targets 80%)")
        print(f"  lift = MDE: range covers all extra orders:   {((lift.lo <= all_) & (all_ <= lift.hi)).mean():.1%}  (90% nominal)")
        print(f"  lift = MDE: range covers test-window orders: {((lift.lo <= win) & (win <= lift.hi)).mean():.1%}")
        print(f"  lift = MDE: range wholly below the truth:    {(lift.hi < all_).mean():.1%}  (5% nominal)")
        print(f"  lift = MDE: range wholly above the truth:    {(lift.lo > all_).mean():.1%}  (5% nominal)")
        print(f"  lift = MDE: wrongly 'no detectable lift':    {(lift.verdict == 'no_detectable_lift').mean():.1%}")
        print(f"  mean bias vs all extra orders:        {((lift.estimate - all_) / all_).mean():+.1%}")
        print(f"  mean bias vs test-window orders:      {((lift.estimate - win) / win).mean():+.1%}")
        print(f"  share of the effect after the test:   {((all_ - win) / all_).mean():.1%}")
        print(f"  median planned MDE:                   {lift.mde.median():.1%}")


if __name__ == "__main__":
    main()
