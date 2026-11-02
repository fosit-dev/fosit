"""Calibration study (METHODOLOGY.md §5.6, §13.6): do FOSIT's ranges hold the truth as often as they claim?

    python validation/calibration_study.py --design cells|holdout --unit state|cbsa [--seeds 200]
                                           [--placebos 40] [--workers 4]

For each seed: synthetic daily orders (50 states + DC, or the 250 largest metro areas), plan
exactly as the app does (api.find_designs: market search, then power), then read the plan twice:
once with no effect, once with extra orders equal to the planned minimum detectable lift added to
the first cell's markets (all campaign markets for a holdout) on ads-on days. `--placebos 0` reads
without placebo calibration, for comparison. Reports how often the 90% range covers the truth,
false positives, detections, bias, and (two cells) how often the head-to-head range covers the
true difference. Everything is seeded; the same command gives the same table.
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


def panel_for(unit: str, seed: int) -> pd.DataFrame:
    attrs = api.geo_attributes(unit)
    start = (pd.Timestamp(TEST_START) - pd.Timedelta(days=PRE)).strftime("%Y-%m-%d")
    n_days = PRE + TEST_DAYS + COOLDOWN
    if unit == "cbsa":
        end = (pd.Timestamp(start) + pd.Timedelta(days=n_days - 1)).strftime("%Y-%m-%d")
        return synthetic.sample_cbsa_history(attrs, end, n_days=n_days, seed=200 + seed)
    ids = [a["geo_id"] for a in attrs]
    pop = np.array([a["population"] for a in attrs], float)
    sizes = pop / 1e5 * 2.0 * np.exp(np.random.default_rng(100 + seed).normal(0, 0.25, len(ids)))
    return synthetic.make_panel(n_days=n_days, start=start, seed=200 + seed, geo_ids=ids, sizes=sizes)[0]


def one_seed(args) -> list[dict]:
    seed, design, unit, placebos = args
    holdout = design == "holdout"
    df = panel_for(unit, seed)
    api.load_history(df[df.date < TEST_START].to_csv(index=False), unit)
    n_cells = 1 if holdout else 2
    found = api.find_designs({"design": "national_holdout" if holdout else "geo_cells", "n_cells": n_cells,
                              "pre_days": PRE, "durations": [TEST_DAYS], "seed": seed, "budgets": [100000] * n_cells,
                              "power_designs": 3, "placebos": placebos})
    if not found["designs"]:
        return []
    d = found["designs"][0]
    mde = d["power"]["cells"][0]["curves"][0]["mde"] or 0.3
    start = (pd.Timestamp(TEST_START) - pd.Timedelta(days=PRE)).strftime("%Y-%m-%d")
    test_end = (pd.Timestamp(TEST_START) + pd.Timedelta(days=TEST_DAYS - 1)).strftime("%Y-%m-%d")
    commitment = {
        "dates": {"pre_start": start, "pre_end": (pd.Timestamp(TEST_START) - pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                  "test_start": TEST_START, "test_end": test_end,
                  "cooldown_end": (pd.Timestamp(test_end) + pd.Timedelta(days=COOLDOWN)).strftime("%Y-%m-%d")},
        "method": {"alpha": 0.1, "report_levels": [0.9], "permutations": {"kind": "moving_block"}, "test_statistic": "abs_sum",
                   "fixed_effects": True, "donor_min_nonzero_share": 0.5, "seed": seed,
                   **({"placebo_calibration": {"n": placebos}} if placebos else {})},
        "cells": [{"id": f"cell_{i + 1}", "label": f"Cell {i + 1}", "geo_ids": g, "budget": 100000} for i, g in enumerate(d["cells"])],
        "control": {"geo_ids": d["control"]}, "excluded": {"geo_ids": []}, "kpi": {"primary": "orders", "secondary": []},
        "thresholds": {"pre_fit_nrmse_max": {}, "leakage_warn_share": 0.05, "spend_share_tolerance_pp": 5,
                       "min_budget_delivery": 0.9, "power_target": 0.8},
        "decision": {"primary_metric": "cell_lift", "meaningful_effect_basis": "planned_mde", "planned_mde_lift": {"cell_1": mde}},
    }
    if holdout:
        commitment["design"] = {"type": "national_holdout", "ads_before_test": "off"}
    out = []
    for multiple in (0.0, 1.0):
        full = df.copy()
        mask = full.geo_id.isin(d["cells"][0]) & full.date.between(TEST_START, test_end)
        extra = np.random.default_rng(seed).poisson(multiple * mde * full.loc[mask, "orders"].to_numpy())
        full.loc[mask, "orders"] += extra
        panel, _ = load_kpi_history(full.to_csv(index=False))
        r = run_read(panel, commitment, None, "2027-01-01")
        for i, cell in enumerate(r["cells"]):
            m = cell["kpis"]["orders"]
            lo, hi = m["intervals"]["0.9"]["incremental"]
            truth = int(extra.sum()) if i == 0 else 0
            out.append({"multiple": multiple, "cell": i, "mde": mde, "truth": truth, "estimate": m["incremental"],
                        "covered": lo <= truth <= hi, "verdict": cell["verdict"]})
        for h in r["head_to_head"]:
            iv = h["metrics"]["delta_incremental"]["intervals"]["0.9"]
            out.append({"multiple": multiple, "cell": "h2h", "covered": iv is not None and iv[0] <= int(extra.sum()) <= iv[1]})
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--design", choices=["cells", "holdout"], default="holdout")
    p.add_argument("--unit", choices=["state", "cbsa"], default="state")
    p.add_argument("--seeds", type=int, default=200)
    p.add_argument("--placebos", type=int, default=40)
    p.add_argument("--workers", type=int, default=4)
    a = p.parse_args()
    with ProcessPoolExecutor(a.workers) as pool:
        rows = [r for rs in pool.map(one_seed, [(s, a.design, a.unit, a.placebos) for s in range(a.seeds)]) for r in rs]
    r = pd.DataFrame(rows)
    cells = r[r.cell != "h2h"]
    null, lift = cells[cells.multiple == 0], cells[(cells.multiple > 0) & (cells.cell == 0)]
    print(f"{a.design} on {a.unit}, {a.seeds} seeds, placebos={a.placebos}")
    print(f"  90% range covers zero (no effect):   {null.covered.mean():.1%}  ({len(null)} cells)")
    print(f"  'positive' with no effect:           {(null.verdict == 'positive').mean():.1%}")
    print(f"  90% range covers truth (lift = MDE): {lift.covered.mean():.1%}  ({len(lift)} cells)")
    print(f"  'positive' with lift = MDE:          {(lift.verdict == 'positive').mean():.1%}  (plan targets 80%)")
    print(f"  mean bias, incremental orders:       {((lift.estimate - lift.truth) / lift.truth).mean():+.1%}")
    print(f"  median planned MDE:                  {lift.mde.median():.1%}")
    h = r[r.cell == "h2h"]
    if len(h):
        print(f"  head-to-head range covers the true difference: {h[h.multiple == 0].covered.mean():.1%} (no effect), "
              f"{h[h.multiple > 0].covered.mean():.1%} (lift in cell 1)")


if __name__ == "__main__":
    main()
