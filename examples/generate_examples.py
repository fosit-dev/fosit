"""Generate FOSIT's example datasets with a known truth.

    python examples/generate_examples.py [two_vendor | national_holdout | vendor_split]   (default: all)

Writes four scenarios, each a complete, realistic test you can load into the app:

  examples/two_vendor/        Vendor A gets 1.5x its cell's planned minimum detectable lift (the test should find it);
                              Vendor B gets 0.5x its cell's (the test has low power for it: it may or may not be
                              confirmed, but either way its interval must contain the truth)
  examples/null_effect/       same markets, no effect at all
  examples/national_holdout/  one campaign on US states, running everywhere except a planned holdout
                              (METHODOLOGY.md §13); the campaign markets get 1.5x the planned MDE
  examples/vendor_split/      two vendors split every state that isn't held out (§13.7); Vendor A gets 1.5x its
                              planned MDE, Vendor B 0.5x

The lift rules are fixed in advance relative to the plan's own sensitivity (not tuned to the result).

Each folder has:
  history_for_planning.csv   26 weeks of daily sales by CBSA (what you'd have when planning)
  plan.fosit-plan.json       a locked plan built from that history (market search + power, like the app)
  kpi_history.csv            history + test + cooldown (what you'd load to read results)
  spend_delivery.csv         each cell's spend and impressions by market, with a little realistic leakage
  truth.json                 the exact incremental orders and revenue we added, and the true iCPA/iROAS

How the effect is added: the base data are generated once (core/fosit/synthetic.py). Planning
uses only the history. The effect is then ADDED as extra orders, Poisson(lift x that day's
orders), in each cell's markets on ads-on days only (none in cooldown). The history the plan
was built on is untouched, and the truth is the exact number of orders we added: the
quantity FOSIT estimates.
"""

import hashlib
import io
import json
import os
import sys
import zipfile

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "core"))
from fosit import api, synthetic  # noqa: E402

SEED = 2026            # fixed before looking at any result
TEST_START = "2026-09-07"   # a Monday
PRE_DAYS, TEST_DAYS, COOLDOWN = 182, 28, 7
BUDGETS = [50_000, 50_000]
LABELS = ["Vendor A", "Vendor B"]
CPM = 25.0
SCENARIOS = {"two_vendor": [1.5, 0.5], "null_effect": [0.0, 0.0]}   # multiples of each cell's planned MDE


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def core_sha256() -> str:
    """Same reproducible zip as web/scripts/build_core_bundle.py, computed in memory."""
    buf = io.BytesIO()
    paths = []
    for root, dirs, names in os.walk(os.path.join(ROOT, "core", "fosit")):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for n in sorted(names):
            if n.endswith((".py", ".csv", ".json", ".md")):
                p = os.path.join(root, n)
                paths.append((p, os.path.relpath(p, os.path.join(ROOT, "core")).replace(os.sep, "/")))
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p, arc in sorted(paths, key=lambda x: x[1]):
            info = zipfile.ZipInfo(arc, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(p, "rb") as f:
                z.writestr(info, f.read())
    return sha256(buf.getvalue())


def plan_hash(commitment: dict) -> str:
    # The documented one-liner (docs/PREREGISTRATION.md); equals RFC 8785 for FOSIT plans.
    return sha256(json.dumps(commitment, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())


def main() -> None:
    attrs = api.geo_attributes("cbsa")
    pop = {a["geo_id"]: a["population"] for a in attrs}
    pre_start = (pd.Timestamp(TEST_START) - pd.Timedelta(days=PRE_DAYS)).strftime("%Y-%m-%d")
    total_days = PRE_DAYS + TEST_DAYS + COOLDOWN
    end = (pd.Timestamp(pre_start) + pd.Timedelta(days=total_days - 1)).strftime("%Y-%m-%d")
    base = synthetic.sample_cbsa_history(attrs, end, n_days=total_days, seed=SEED)
    history = base[base["date"] < TEST_START].reset_index(drop=True)
    history_csv = history.to_csv(index=False)

    # Plan exactly as the app does: market search ranked by sensitivity (api.find_designs), take design 1
    loaded = api.load_history(history_csv, "cbsa")
    assert loaded["ok"], loaded["issues"]
    found = api.find_designs({"n_cells": 2, "kpi": "orders", "pre_days": PRE_DAYS, "durations": [TEST_DAYS],
                              "cooldown_days": COOLDOWN, "seed": SEED, "budgets": BUDGETS})
    best = found["designs"][0]

    class D:  # minimal view of the chosen design
        cells, control, fit, shares, balance_score = best["cells"], best["control"], best["fit"], best["shares"], best["balance_score"]
        pre_fit = best["pre_fit"]
    design = D
    mde = [c["curves"][0]["mde"] for c in best["power"]["cells"]]
    sel = {"funnel": found["funnel"]}
    print("design:", [len(c) for c in design.cells], "fit", [round(f, 3) for f in design.fit], "MDE", mde)

    with open(os.path.join(ROOT, "core", "fosit", "geo_data", "SOURCES.json")) as f:
        mapping_sha = json.load(f)["outputs"]["zcta_to_geo.csv"]["sha256"]
    test_end = (pd.Timestamp(TEST_START) + pd.Timedelta(days=TEST_DAYS - 1)).strftime("%Y-%m-%d")

    for name, lifts in SCENARIOS.items():
        folder = os.path.join(HERE, name)
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "history_for_planning.csv"), "w") as f:
            f.write(history_csv)

        # --- the effect: extra orders on ads-on days, from a separate random stream ---
        rng = np.random.default_rng(SEED + 1)
        full = base.copy()
        aov = (full["revenue"] / full["orders"].where(full["orders"] > 0)).fillna(full["revenue"].sum() / full["orders"].sum())
        truth = {}
        for k, (cell, multiple) in enumerate(zip(design.cells, lifts)):
            lift = round(multiple * mde[k], 4)
            mask = full["geo_id"].isin(cell) & full["date"].between(TEST_START, test_end)
            extra = rng.poisson(lift * full.loc[mask, "orders"].to_numpy()) if lift > 0 else np.zeros(mask.sum(), int)
            full.loc[mask, "orders"] += extra
            extra_rev = np.round(extra * aov[mask].to_numpy(), 2)
            full.loc[mask, "revenue"] = np.round(full.loc[mask, "revenue"] + extra_rev, 2)
            truth[f"cell_{k + 1}"] = {"label": LABELS[k], "injected_lift": lift, "planned_mde": mde[k], "multiple_of_mde": multiple,
                                      "true_incremental_orders": int(extra.sum()),
                                      "true_incremental_revenue": float(np.round(extra_rev.sum(), 2)),
                                      "spend": BUDGETS[k],
                                      "true_icpa": BUDGETS[k] / extra.sum() if extra.sum() > 0 else None,
                                      "true_iroas": float(extra_rev.sum() / BUDGETS[k])}
        full.to_csv(os.path.join(folder, "kpi_history.csv"), index=False)

        # --- spend & delivery: even daily spend, impressions by population, a little leakage ---
        rows = []
        days = pd.date_range(TEST_START, test_end).strftime("%Y-%m-%d")
        leak_geos = design.control[:3]
        for k, cell in enumerate(design.cells):
            label, daily = LABELS[k], BUDGETS[k] / TEST_DAYS
            weights = np.array([pop[g] for g in cell], float)
            weights /= weights.sum()
            for day in days:
                imps = daily / CPM * 1000
                own = 0.985 if k == 0 else 0.995
                for g, w in zip(cell, weights):
                    rows.append((day, label, g, int(round(imps * own * w)), round(daily * own * w, 2)))
                if k == 0:   # 1.5% of Vendor A's delivery spills into three control markets
                    for g in leak_geos:
                        rows.append((day, label, g, int(round(imps * 0.005)), round(daily * 0.005, 2)))
                else:        # 0.5% of Vendor B's delivery can't be attributed to a market
                    rows.append((day, label, "*", int(round(imps * 0.005)), round(daily * 0.005, 2)))
        pd.DataFrame(rows, columns=["date", "cell", "geo_id", "impressions", "spend"]).to_csv(
            os.path.join(folder, "spend_delivery.csv"), index=False)

        # --- the locked plan (same structure the web app builds; schema/locked_plan.schema.json) ---
        cells = [{"id": f"cell_{k + 1}", "label": LABELS[k], "geo_ids": sorted(design.cells[k]), "budget": BUDGETS[k]}
                 for k in range(2)]
        fit_limit = {c["id"]: {kpi: round(min(1.5 * max(design.fit[k], design.pre_fit[k]), 0.15), 4) for kpi in ("orders", "revenue")}
                     for k, c in enumerate(cells)}
        commitment = {
            "tool": {"name": "FOSIT", "version": "0.1.0", "core_sha256": core_sha256()},
            "created_at": "2026-09-01T09:00:00Z",
            "test_name": "Example: two-vendor CTV test" if name == "two_vendor" else "Example: null effect",
            "advertiser_label": "Synthetic example (not real data)",
            "currency": "USD",
            "geo": {"unit": "cbsa", "mapping_name": "Census 2020 ZCTA-county + OMB July 2023 CBSA delineation (FOSIT geo_data)",
                    "mapping_sha256": mapping_sha},
            "kpi": {"primary": "orders", "secondary": ["revenue"], "aggregation": "daily"},
            "dates": {"pre_start": pre_start, "pre_end": (pd.Timestamp(TEST_START) - pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                      "test_start": TEST_START, "test_end": test_end,
                      "cooldown_end": (pd.Timestamp(test_end) + pd.Timedelta(days=COOLDOWN)).strftime("%Y-%m-%d")},
            "cells": cells,
            "control": {"geo_ids": sorted(design.control)},
            "excluded": {"geo_ids": []},
            "method": {"estimator": "ridge_ascm", "fixed_effects": True, "lambda_selection": "cv_1se", "inference": "conformal",
                       "permutations": {"kind": "moving_block"}, "placebo_calibration": {"n": 40},
                       "test_statistic": "abs_sum", "alpha": 0.1,
                       "report_levels": [0.9, 0.95], "head_to_head": "joint_conformal_projection",
                       "donor_min_nonzero_share": 0.5, "seed": SEED},
            "thresholds": {"pre_fit_nrmse_max": fit_limit, "leakage_warn_share": 0.05, "spend_share_tolerance_pp": 5,
                           "min_budget_delivery": 0.9, "power_target": 0.8},
            "decision": {"primary_metric": "delta_icpa", "meaningful_effect_basis": "planned_mde",
                         "planned_mde_lift": {c["id"]: round(mde[k], 4) for k, c in enumerate(cells) if mde[k]}},
            "assignment": {"method": "stratified_random_search", "candidates_searched": sel["funnel"]["generated"],
                           "design_rank": 1, "label_assignment": "user"},
            "vendor_targeting_confirmed": [{"cell_id": c["id"], "confirmed": True} for c in cells],
            "data_fingerprint": {"kpi_history_sha256": sha256(history_csv.encode()), "rows": len(history),
                                 "geos": int(history["geo_id"].nunique()), "first_date": history["date"].min(),
                                 "last_date": history["date"].max()},
        }
        plan = {"fosit_plan_version": "1.0", "commitment": commitment,
                "hash": {"algorithm": "SHA-256", "canonicalization": "RFC8785", "value": plan_hash(commitment)},
                "appendix": {"note": "Design diagnostics. Not part of the fingerprint.",
                             "design": {"fit": design.fit, "shares": design.shares, "balance_score": design.balance_score},
                             "mde": [{"label": LABELS[k], "test_days": TEST_DAYS, "mde": mde[k]} for k in range(2)]}}
        with open(os.path.join(folder, "plan.fosit-plan.json"), "w") as f:
            json.dump(plan, f, indent=2)
        with open(os.path.join(folder, "truth.json"), "w") as f:
            json.dump({"scenario": name, "seed": SEED, "cells": truth,
                       "note": "Exact orders and revenue added on ads-on days. FOSIT should recover these within its intervals."}, f, indent=2)
        print(name, json.dumps({k: (v["true_incremental_orders"], v["true_icpa"]) for k, v in truth.items()}))


# State-level holdout scenarios (§13): (labels, budgets, multiples of each cell's planned MDE, test name).
# Multiples are fixed before looking at any result, as above.
HOLDOUT_SCENARIOS = {
    "national_holdout": (["CTV campaign"], [400_000], [1.5], "Example: national CTV campaign with a state holdout"),
    "vendor_split": (["Vendor A", "Vendor B"], [200_000, 200_000], [1.5, 0.5],
                     "Example: two vendors split the country, with a no-CTV holdout"),
}


def holdout_example(name: str) -> None:
    """US states with a holdout chosen by the planner (§13); with two cells, the vendors split every other state (§13.7)."""
    labels, budgets, multiples, test_name = HOLDOUT_SCENARIOS[name]
    k = len(labels)
    attrs = api.geo_attributes("state")
    pop = {a["geo_id"]: a["population"] for a in attrs}
    pre_start = (pd.Timestamp(TEST_START) - pd.Timedelta(days=PRE_DAYS)).strftime("%Y-%m-%d")
    total_days = PRE_DAYS + TEST_DAYS + COOLDOWN
    end = (pd.Timestamp(pre_start) + pd.Timedelta(days=total_days - 1)).strftime("%Y-%m-%d")
    base = synthetic.sample_state_history(attrs, end, n_days=total_days, seed=SEED)
    history = base[base["date"] < TEST_START].reset_index(drop=True)
    history_csv = history.to_csv(index=False)

    assert api.load_history(history_csv, "state")["ok"]
    found = api.find_designs({"design": "national_holdout", "n_cells": k, "kpi": "orders", "pre_days": PRE_DAYS,
                              "durations": [TEST_DAYS], "cooldown_days": COOLDOWN, "seed": SEED, "budgets": budgets})
    best = found["designs"][0]
    holdout = best["control"]
    mde = [c["curves"][0]["mde"] for c in best["power"]["cells"]]
    print(f"{name} design:", [len(c) for c in best["cells"]], "with ads,", len(holdout), "held out",
          round(best["control_share"], 3), "of sales; fit", [round(f, 3) for f in best["fit"]], "MDE", mde)

    folder = os.path.join(HERE, name)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "history_for_planning.csv"), "w") as f:
        f.write(history_csv)
    test_end = (pd.Timestamp(TEST_START) + pd.Timedelta(days=TEST_DAYS - 1)).strftime("%Y-%m-%d")

    rng = np.random.default_rng(SEED + 1)
    full = base.copy()
    aov = (full["revenue"] / full["orders"].where(full["orders"] > 0)).fillna(full["revenue"].sum() / full["orders"].sum())
    truth, rows = {}, []
    days = pd.date_range(TEST_START, test_end).strftime("%Y-%m-%d")
    for i, (cell, label, budget, multiple) in enumerate(zip(best["cells"], labels, budgets, multiples)):
        lift = round(multiple * mde[i], 4)
        mask = full["geo_id"].isin(cell) & full["date"].between(TEST_START, test_end)
        extra = rng.poisson(lift * full.loc[mask, "orders"].to_numpy())
        full.loc[mask, "orders"] += extra
        extra_rev = np.round(extra * aov[mask].to_numpy(), 2)
        full.loc[mask, "revenue"] = np.round(full.loc[mask, "revenue"] + extra_rev, 2)
        truth[f"cell_{i + 1}"] = {"label": label, "injected_lift": lift, "planned_mde": mde[i], "multiple_of_mde": multiple,
                                  "true_incremental_orders": int(extra.sum()),
                                  "true_incremental_revenue": float(np.round(extra_rev.sum(), 2)),
                                  "spend": budget, "true_icpa": budget / extra.sum(),
                                  "true_iroas": float(extra_rev.sum() / budget)}
        # spend & delivery: even daily spend by population across the cell's states, 0.5% not attributable to a state
        weights = np.array([pop[g] for g in cell], float)
        weights /= weights.sum()
        daily = budget / TEST_DAYS
        for day in days:
            imps = daily / CPM * 1000
            for g, w in zip(cell, weights):
                rows.append((day, label, g, int(round(imps * 0.995 * w)), round(daily * 0.995 * w, 2)))
            rows.append((day, label, "*", int(round(imps * 0.005)), round(daily * 0.005, 2)))
    full.to_csv(os.path.join(folder, "kpi_history.csv"), index=False)
    pd.DataFrame(rows, columns=["date", "cell", "geo_id", "impressions", "spend"]).to_csv(
        os.path.join(folder, "spend_delivery.csv"), index=False)

    with open(os.path.join(ROOT, "core", "fosit", "geo_data", "SOURCES.json")) as f:
        mapping_sha = json.load(f)["outputs"]["zcta_to_geo.csv"]["sha256"]
    cells = [{"id": f"cell_{i + 1}", "label": labels[i], "geo_ids": sorted(c), "budget": budgets[i]} for i, c in enumerate(best["cells"])]
    commitment = {
        "tool": {"name": "FOSIT", "version": "0.1.0", "core_sha256": core_sha256()},
        "created_at": "2026-09-01T09:00:00Z",
        "test_name": test_name,
        "advertiser_label": "Synthetic example (not real data)",
        "currency": "USD",
        "geo": {"unit": "state", "mapping_name": "Census 2020 ZCTA-county relationship, by state (FOSIT geo_data)",
                "mapping_sha256": mapping_sha},
        "kpi": {"primary": "orders", "secondary": ["revenue"], "aggregation": "daily"},
        "dates": {"pre_start": pre_start, "pre_end": (pd.Timestamp(TEST_START) - pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                  "test_start": TEST_START, "test_end": test_end,
                  "cooldown_end": (pd.Timestamp(test_end) + pd.Timedelta(days=COOLDOWN)).strftime("%Y-%m-%d")},
        "design": {"type": "national_holdout", "ads_before_test": "off"},
        "cells": cells,
        "control": {"geo_ids": sorted(holdout)},
        "excluded": {"geo_ids": []},
        "method": {"estimator": "ridge_ascm", "fixed_effects": True, "lambda_selection": "cv_1se", "inference": "conformal",
                   "permutations": {"kind": "moving_block"}, "placebo_calibration": {"n": 40},
                   "test_statistic": "abs_sum", "alpha": 0.1,
                   "report_levels": [0.9, 0.95], "head_to_head": "joint_conformal_projection",
                   "donor_min_nonzero_share": 0.5, "seed": SEED},
        "thresholds": {"pre_fit_nrmse_max": {c["id"]: {kpi: round(min(1.5 * max(best["fit"][i], best["pre_fit"][i]), 0.15), 4)
                                                   for kpi in ("orders", "revenue")} for i, c in enumerate(cells)},
                       "leakage_warn_share": 0.05, "spend_share_tolerance_pp": 5, "min_budget_delivery": 0.9, "power_target": 0.8},
        "decision": {"primary_metric": "cell_lift" if k == 1 else "delta_icpa", "meaningful_effect_basis": "planned_mde",
                     "planned_mde_lift": {c["id"]: round(mde[i], 4) for i, c in enumerate(cells)}},
        "assignment": {"method": "stratified_random_search", "candidates_searched": found["funnel"]["generated"],
                       "design_rank": 1, "label_assignment": "user"},
        "vendor_targeting_confirmed": [{"cell_id": c["id"], "confirmed": True} for c in cells],
        "data_fingerprint": {"kpi_history_sha256": sha256(history_csv.encode()), "rows": len(history),
                             "geos": int(history["geo_id"].nunique()), "first_date": history["date"].min(),
                             "last_date": history["date"].max()},
    }
    plan = {"fosit_plan_version": "1.0", "commitment": commitment,
            "hash": {"algorithm": "SHA-256", "canonicalization": "RFC8785", "value": plan_hash(commitment)},
            "appendix": {"note": "Design diagnostics. Not part of the fingerprint.",
                         "design": {"fit": best["fit"], "shares": best["shares"], "balance": best["balance"],
                                    "holdout_share": best["control_share"]},
                         "mde": [{"label": labels[i], "test_days": TEST_DAYS, "mde": mde[i]} for i in range(k)]}}
    with open(os.path.join(folder, "plan.fosit-plan.json"), "w") as f:
        json.dump(plan, f, indent=2)
    with open(os.path.join(folder, "truth.json"), "w") as f:
        json.dump({"scenario": name, "seed": SEED, "cells": truth,
                   "note": "Exact orders and revenue added in each cell's states on ads-on days. FOSIT should recover these within its intervals."},
                  f, indent=2)
    print(name, json.dumps({c: (v["true_incremental_orders"], v["true_icpa"]) for c, v in truth.items()}))


if __name__ == "__main__":
    which = sys.argv[1:] or ["two_vendor", *HOLDOUT_SCENARIOS]
    if "two_vendor" in which:
        main()
    for name in HOLDOUT_SCENARIOS:
        if name in which:
            holdout_example(name)
