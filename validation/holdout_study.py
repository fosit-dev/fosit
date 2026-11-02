"""National holdout study (METHODOLOGY.md §13.6): does the holdout read recover known effects on state data?

    python validation/holdout_study.py [--seeds 200] [--share-min 0.10] [--share-max 0.20] [--workers 4]

For each seed: synthetic daily orders for the 50 states + DC (core/fosit/synthetic.py), plan a
national holdout exactly as the app does (api.find_designs), then read it twice: once with no
effect, once with extra orders equal to the planned minimum detectable lift added to the campaign
states on ads-on days. Reports how often the 90% interval covers the truth, false positives,
detections, and bias. Everything is seeded; the same command gives the same table.
"""

import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "core"))
from fosit import api, synthetic  # noqa: E402
from fosit.panel import load_kpi_history  # noqa: E402
from fosit.read import run_read  # noqa: E402

TEST_START, PRE, TEST_DAYS, COOLDOWN = "2026-09-07", 126, 28, 7


def one_seed(args) -> list[dict]:
    seed, share_min, share_max = args
    attrs = api.geo_attributes("state")
    ids = [a["geo_id"] for a in attrs]
    pop = np.array([a["population"] for a in attrs], float)
    rng = np.random.default_rng(100 + seed)
    sizes = pop / 1e5 * 2.0 * np.exp(rng.normal(0, 0.25, len(ids)))
    start = (pd.Timestamp(TEST_START) - pd.Timedelta(days=PRE)).strftime("%Y-%m-%d")
    df, _ = synthetic.make_panel(n_days=PRE + TEST_DAYS + COOLDOWN, start=start, seed=200 + seed, geo_ids=ids, sizes=sizes)
    api.load_history(df[df.date < TEST_START].to_csv(index=False), "state")
    found = api.find_designs({"design": "national_holdout", "pre_days": PRE, "durations": [TEST_DAYS], "seed": seed,
                              "budgets": [200000], "power_designs": 3, "share_min": share_min, "share_max": share_max})
    if not found["designs"]:
        return [{"seed": seed, "design": False}]
    d = found["designs"][0]
    mde = d["power"]["cells"][0]["curves"][0]["mde"] or 0.2
    campaign, holdout = d["cells"][0], d["control"]
    test_end = (pd.Timestamp(TEST_START) + pd.Timedelta(days=TEST_DAYS - 1)).strftime("%Y-%m-%d")
    commitment = {
        "dates": {"pre_start": start, "pre_end": (pd.Timestamp(TEST_START) - pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                  "test_start": TEST_START, "test_end": test_end,
                  "cooldown_end": (pd.Timestamp(test_end) + pd.Timedelta(days=COOLDOWN)).strftime("%Y-%m-%d")},
        "design": {"type": "national_holdout", "ads_before_test": "off"},
        "method": {"alpha": 0.1, "report_levels": [0.9], "permutations": {"kind": "moving_block"}, "test_statistic": "abs_sum",
                   "fixed_effects": True, "donor_min_nonzero_share": 0.5},
        "cells": [{"id": "cell_1", "label": "Campaign", "geo_ids": campaign, "budget": 200000}],
        "control": {"geo_ids": holdout}, "excluded": {"geo_ids": []}, "kpi": {"primary": "orders", "secondary": []},
        "thresholds": {"pre_fit_nrmse_max": {}, "leakage_warn_share": 0.05, "spend_share_tolerance_pp": 5,
                       "min_budget_delivery": 0.9, "power_target": 0.8},
        "decision": {"primary_metric": "cell_lift", "meaningful_effect_basis": "planned_mde", "planned_mde_lift": {"cell_1": mde}},
    }
    out = []
    for multiple in (0.0, 1.0):
        full = df.copy()
        mask = full.geo_id.isin(campaign) & full.date.between(TEST_START, test_end)
        extra = np.random.default_rng(seed).poisson(multiple * mde * full.loc[mask, "orders"].to_numpy())
        full.loc[mask, "orders"] += extra
        panel, _ = load_kpi_history(full.to_csv(index=False))
        cell = run_read(panel, commitment, None, "2027-01-01")["cells"][0]
        m = cell["kpis"]["orders"]
        lo, hi = m["intervals"]["0.9"]["incremental"]
        truth = int(extra.sum())
        out.append({"seed": seed, "design": True, "multiple": multiple, "held_out": len(holdout), "mde": mde, "truth": truth,
                    "estimate": m["incremental"], "lo": lo, "hi": hi, "verdict": cell["verdict"], "covered": lo <= truth <= hi})
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--seeds", type=int, default=200)
    p.add_argument("--share-min", type=float, default=0.10)
    p.add_argument("--share-max", type=float, default=0.20)
    p.add_argument("--workers", type=int, default=4)
    a = p.parse_args()
    with ProcessPoolExecutor(a.workers) as pool:
        rows = [r for rs in pool.map(one_seed, [(s, a.share_min, a.share_max) for s in range(a.seeds)]) for r in rs]
    r = pd.DataFrame([x for x in rows if x["design"]])
    null, lift = r[r.multiple == 0], r[r.multiple > 0]
    print(f"seeds {a.seeds}, with a design {len(null)}; holdout {a.share_min:.0%}-{a.share_max:.0%}, median {null.held_out.median():.0f} markets")
    print(f"90% interval covers zero (no effect):     {int(null.covered.sum())} / {len(null)}")
    print(f"90% interval covers truth (lift = MDE):   {int(lift.covered.sum())} / {len(lift)} ({lift.covered.mean():.0%})")
    print(f"'positive' with no effect:                {int((null.verdict == 'positive').sum())} / {len(null)}")
    print(f"'negative' with no effect:                {int((null.verdict == 'negative').sum())} / {len(null)}")
    print(f"'positive' with lift = MDE:               {int((lift.verdict == 'positive').sum())} / {len(lift)} ({(lift.verdict == 'positive').mean():.0%})")
    print(f"mean bias, incremental orders:            {((lift.estimate - lift.truth) / lift.truth).mean():+.1%}")
    print(f"median planned MDE:                       {lift.mde.median():.1%}")


if __name__ == "__main__":
    main()
