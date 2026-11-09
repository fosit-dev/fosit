"""Crossover study (METHODOLOGY.md §14.5): is the geo crossover honest and as sensitive as planned for small advertisers?

    python validation/crossover_study.py [--orders-per-day 100] [--seeds 200] [--half-life 3] [--block-days 14] [--blocks 8]

For each seed: synthetic daily orders for the 50 states + DC (core/fosit/synthetic.py) at the given national volume,
26 weeks of history, then the test period. Plan exactly as the app does (api.find_designs, design crossover), draw a
random schedule, and read the test twice: with no effect, and with the planned minimum detectable lift added to whichever
half has the ads, building up and fading with the given half-life (days). Everything is seeded.
"""

import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "core"))
from fosit import api, crossover, synthetic  # noqa: E402
from fosit.panel import load_kpi_history  # noqa: E402
from fosit.read import run_read  # noqa: E402

HISTORY, TEST_START = 182, "2027-01-04"


def one_seed(args) -> list[dict]:
    seed, per_day, half_life, L, B = args
    attrs = api.geo_attributes("state")
    ids = [a["geo_id"] for a in attrs]
    per_100k = per_day / (sum(a["population"] for a in attrs) / 1e5)
    days = HISTORY + L * B
    start = (pd.Timestamp(TEST_START) - pd.Timedelta(days=HISTORY)).strftime("%Y-%m-%d")
    end = (pd.Timestamp(start) + pd.Timedelta(days=days - 1)).strftime("%Y-%m-%d")
    df = synthetic.sample_state_history(attrs, end, n_days=days, seed=300 + seed, orders_per_100k=per_100k)
    api.load_history(df[df.date < TEST_START].to_csv(index=False), "state")
    found = api.find_designs({"design": "crossover", "block_days": L, "durations": [L * B], "seed": seed, "budgets": [50000],
                              "power_designs": 3})
    if not found["designs"]:
        return [{"none": True}]
    d = found["designs"][0]
    mde = d["power"]["cells"][0]["curves"][0]["mde"] or 0.3
    rng = np.random.default_rng(seed)
    schedule = crossover.random_schedule(B, rng)
    test_end = (pd.Timestamp(TEST_START) + pd.Timedelta(days=L * B - 1)).strftime("%Y-%m-%d")
    c = {"dates": {"pre_start": start, "pre_end": (pd.Timestamp(TEST_START) - pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                   "test_start": TEST_START, "test_end": test_end, "cooldown_end": test_end},
         "design": {"type": "crossover", "block_days": L, "washout_days": crossover.WASHOUT[L], "schedule": schedule},
         "cells": [{"id": "cell_1", "label": "Campaign", "geo_ids": d["cells"][0], "budget": 50000}],
         "control": {"geo_ids": d["control"]}, "excluded": {"geo_ids": []}, "kpi": {"primary": "orders", "secondary": []},
         "method": {"alpha": 0.1, "report_levels": [0.9], "seed": seed},
         "thresholds": {"pre_fit_nrmse_max": {}, "leakage_warn_share": 0.05, "spend_share_tolerance_pp": 5,
                        "min_budget_delivery": 0.9, "power_target": 0.8},
         "decision": {"primary_metric": "cell_lift", "meaningful_effect_basis": "planned_mde", "planned_mde_lift": {"cell_1": mde}}}
    out = []
    test = df.date >= TEST_START
    day = (pd.to_datetime(df.date) - pd.Timestamp(TEST_START)).dt.days
    on_a = np.repeat([1.0 if x == "A" else 0.0 for x in schedule], L)
    for multiple in (0.0, 1.0):
        full = df.copy()
        extra = np.zeros(len(full))
        if multiple:
            for half, on in ((set(d["cells"][0]), on_a), (set(d["control"]), 1 - on_a)):
                share = crossover.adstock(on, half_life)
                m = test & full.geo_id.isin(half)
                lam = full.loc[m, "orders"].to_numpy() * mde * share[day[m].to_numpy()]
                extra[m.to_numpy()] = np.random.default_rng(seed + 7).poisson(lam)
        full["orders"] = full["orders"] + extra
        panel, _ = load_kpi_history(full.to_csv(index=False))
        cell = run_read(panel, c, None, "2027-12-31")["cells"][0]
        m = cell["kpis"]["orders"]
        lo, hi = m["intervals"]["0.9"]["incremental"]
        truth = float(extra.sum())
        out.append({"multiple": multiple, "mde": mde, "truth": truth, "estimate": m["incremental"], "lo": lo, "hi": hi,
                    "covered": lo <= truth <= hi, "verdict": cell["verdict"]})
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--orders-per-day", type=float, default=100)
    p.add_argument("--seeds", type=int, default=200)
    p.add_argument("--half-life", type=float, default=3.0)
    p.add_argument("--block-days", type=int, default=14)
    p.add_argument("--blocks", type=int, default=8)
    p.add_argument("--workers", type=int, default=4)
    a = p.parse_args()
    with ProcessPoolExecutor(a.workers) as pool:
        rows = [r for rs in pool.map(one_seed, [(s, a.orders_per_day, a.half_life, a.block_days, a.blocks) for s in range(a.seeds)]) for r in rs]
    r = pd.DataFrame([x for x in rows if not x.get("none")])
    null, lift = r[r.multiple == 0], r[r.multiple > 0]
    print(f"crossover, {a.orders_per_day:.0f} orders/day, {a.blocks} blocks x {a.block_days} days, effect half-life {a.half_life:g} days, {a.seeds} seeds")
    print(f"  90% range covers zero (no effect):   {null.covered.mean():.1%}")
    print(f"  'positive' with no effect:           {(null.verdict == 'positive').mean():.1%}")
    print(f"  90% range covers truth (lift = MDE): {lift.covered.mean():.1%}")
    print(f"  'positive' with lift = MDE:          {(lift.verdict == 'positive').mean():.1%}  (plan targets 80%)")
    print(f"  mean bias, incremental orders:       {((lift.estimate - lift.truth) / lift.truth).mean():+.1%}")
    print(f"  median planned MDE:                  {lift.mde.median():.1%}")


if __name__ == "__main__":
    main()
