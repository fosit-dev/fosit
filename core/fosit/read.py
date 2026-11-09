"""Read module: results per cell, head-to-head, verdicts and honesty checks.

METHODOLOGY.md §6 (business metrics), §7 (head-to-head), §8 (verdicts), §11 (honesty checks),
§13 (national holdout: the one cell is the campaign's markets, the control is the holdout).
Every analysis choice comes from the locked plan's commitment, never from UI settings.
"""

from __future__ import annotations

import io
import math
from itertools import combinations

import numpy as np
import pandas as pd

from . import conformal
from .estimate import CellEstimate, CellSeries, cell_series, estimate
from .holdout import estimate_holdout
from .placebo import calibrate, placebo_errors
from .panel import Panel
from .spend import SpendData, leakage

H2H_GRID = 41


def thresholds_period(c: dict) -> str:
    """How the plan judges pre-period fit: "day" (default, and every plan before FOSIT 0.2) or "week" (§9.3)."""
    return c.get("thresholds", {}).get("pre_fit_period", "day")


def _num(x):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else float(x)


def _perms(method: dict) -> conformal.Permutations:
    p = method.get("permutations", {"kind": "moving_block"})
    return conformal.Permutations(p["kind"], n=int(p.get("n", 1000)), seed=int(p.get("seed", method.get("seed", 0))))


def _interval_dict(est: CellEstimate, level: float, scale: float = 1.0) -> list:
    lo, hi = est.intervals[level]
    return [_num(lo * scale), _num(hi * scale)]


def business_metrics(est: CellEstimate, kpi: str, spend: float | None, levels) -> dict:
    """§6: incremental totals, lift, and the spend-based ratios, each with intervals."""
    inc = est.incremental
    out = {
        "kpi": kpi, "att": est.att, "p_value": est.p_value, "pre_fit_nrmse": est.pre_fit_nrmse,
        "observed": est.observed_total, "counterfactual": est.counterfactual_total,
        "incremental": inc, "lift": est.lift,
        "intervals": {}, "spend": spend,
    }
    for lv in levels:
        lo, hi = est.incremental_interval(lv)
        base = est.counterfactual_total
        iv = {"incremental": [_num(lo), _num(hi)], "lift": [_num(lo / base), _num(hi / base)]}
        if spend and spend > 0:
            iv["per_1000"] = [_num(1000 * lo / spend), _num(1000 * hi / spend)]
            if kpi == "orders":
                # S/Delta is decreasing in Delta: low bound from the high incremental bound, and vice versa (§6)
                iv["icpa"] = [_num(spend / hi) if hi > 0 and math.isfinite(hi) else (0.0 if hi == math.inf else None),
                              _num(spend / lo) if lo > 0 else None]
            else:
                iv["iroas"] = [_num(lo / spend), _num(hi / spend)]
        out["intervals"][str(lv)] = iv
    if spend and spend > 0:
        out["per_1000"] = 1000 * inc / spend
        if kpi == "orders":
            out["icpa"] = spend / inc if inc > 0 else None
        else:
            out["iroas"] = inc / spend
    return out


def verdict(est: CellEstimate, level: float, meaningful: float | None, fit_ok: bool) -> tuple[str, str]:
    """§8: positive / negative / no detectable lift / inconclusive, with the reason in plain English."""
    lo, hi = est.incremental_interval(level)
    pct = f"{level:.0%}"
    if not fit_ok:
        return "inconclusive", "The twin didn't track these markets closely enough before the test (pre-period fit check failed)."
    if lo > 0:
        return "positive", f"The {pct} range of incremental results is entirely above zero."
    if hi < 0:
        return "negative", f"The {pct} range is entirely below zero. That's unusual for advertising: check the data and the leakage check."
    if meaningful is None:
        return "inconclusive", f"The {pct} range includes zero, and the plan has no threshold for a worthwhile effect."
    if hi < meaningful:
        return "no_detectable_lift", (f"The {pct} range includes zero, and even its top ({hi:,.0f}) is below the {meaningful:,.0f} "
                                      "needed to be worthwhile, so we can rule out an effect that would pay off.")
    return "inconclusive", (f"The {pct} range includes zero but also effects up to {hi:,.0f}, above the {meaningful:,.0f} needed to be "
                            "worthwhile. The test can't tell either way.")


def _grid_for(series: CellSeries, est: CellEstimate, perms, fixed_effects: bool) -> conformal.CellGrid:
    lo, hi = est.intervals[max(est.intervals)]
    resid_sd = float(np.std((est.observed - est.counterfactual)[: est.n_pre]))
    scale = max(resid_sd / math.sqrt(est.n_post), 1e-9)
    lo = lo if math.isfinite(lo) else est.att - 8 * scale
    hi = hi if math.isfinite(hi) else est.att + 8 * scale
    pad = 0.25 * (hi - lo)
    return conformal.cell_grid(series.y1, series.Y0, series.n_post, est.lam, lo - pad, hi + pad,
                               n=H2H_GRID, fixed_effects=fixed_effects, perms=perms)


def head_to_head(a: dict, b: dict, kpi: str, levels, decision_level: float) -> dict:
    """§7.2: joint conformal region for two cells, projected onto each comparison."""
    ga, gb = a["grid"], b["grid"]
    ea, eb = a["est"], b["est"]
    inc_a, inc_b = ga.taus * ea.scale, gb.taus * eb.scale   # a holdout's scale is negative (§13.4); the grids map the same way
    sa, sb = a["spend"], b["spend"]
    p = conformal.joint_p_values(ga, gb)
    out = {"a": a["id"], "b": b["id"], "kpi": kpi, "metrics": {}, "grid_points": H2H_GRID}
    have_spend = bool(sa and sb and sa > 0 and sb > 0)

    def positive_only(f):
        """iCPA is only defined where both cells have positive incremental orders (§7.1)."""
        return lambda x, y: np.where((x > 0) & (y > 0), f(np.where(x > 0, x, 1.0), np.where(y > 0, y, 1.0)), np.nan)

    metrics = {}
    if have_spend:
        metrics["delta_incremental_per_1000"] = (lambda x, y: 1000 * (x / sa - y / sb),
                                                 1000 * (ea.incremental / sa - eb.incremental / sb), 0.0)
        if kpi == "orders":
            metrics["delta_icpa"] = (positive_only(lambda x, y: sa / x - sb / y),
                                     (sa / ea.incremental - sb / eb.incremental) if ea.incremental > 0 and eb.incremental > 0 else None, 0.0)
            metrics["ratio_icpa"] = (positive_only(lambda x, y: (sa / x) / (sb / y)),
                                     ((sa / ea.incremental) / (sb / eb.incremental)) if ea.incremental > 0 and eb.incremental > 0 else None, 1.0)
        else:
            metrics["delta_iroas"] = (lambda x, y: x / sa - y / sb, ea.incremental / sa - eb.incremental / sb, 0.0)
    metrics["delta_incremental"] = (lambda x, y: x - y, ea.incremental - eb.incremental, 0.0)

    for name, (f, point, null) in metrics.items():
        m = {"estimate": _num(point) if point is not None else None, "null": null, "intervals": {}}
        for lv in levels:
            region = p > round(1 - lv, 12)
            lo, hi = conformal.project(region, inc_a, inc_b, f)
            defined = math.isfinite(lo) and math.isfinite(hi)
            m["intervals"][str(lv)] = [_num(lo), _num(hi)] if defined else None
        iv = m["intervals"].get(str(decision_level))
        m["distinguishable"] = None if iv is None else bool(iv[0] > null or iv[1] < null)
        m["note"] = ("" if iv is not None else
                     "Not defined: at least one cell can't be distinguished from zero incremental orders. Compare incremental orders per 1,000 instead.")
        out["metrics"][name] = m
    return out


def run_read(panel: Panel, commitment: dict, spend: SpendData | None, today: str, appendix: dict | None = None,
             plan_hash: str = "", progress=None) -> dict:
    c = commitment
    if c.get("design", {}).get("type") == "crossover":      # §14: halves take turns; its own exact test
        from .crossover import run_read_crossover
        return run_read_crossover(panel, c, spend, today, plan_hash)
    d = c["dates"]
    method = c["method"]
    alpha = float(method["alpha"])
    levels = tuple(sorted(float(x) for x in method.get("report_levels", [0.9, 0.95])))
    decision_level = round(1 - alpha, 12)
    if decision_level not in levels:
        levels = tuple(sorted(set(levels) | {decision_level}))
    perms = _perms(method)
    fixed_effects = bool(method.get("fixed_effects", True))
    min_nonzero = float(method.get("donor_min_nonzero_share", 0.5))

    errors = []
    first, last = panel.dates[0], panel.dates[-1]
    if pd.Timestamp(d["pre_start"]) < first or pd.Timestamp(d["pre_end"]) > last:
        errors.append(f"The sales file must cover the plan's history period {d['pre_start']} to {d['pre_end']}; "
                      f"it runs {first:%Y-%m-%d} to {last:%Y-%m-%d}.")
    if pd.Timestamp(d["test_start"]) > last:
        errors.append(f"The sales file ends {last:%Y-%m-%d}, before the test started on {d['test_start']}.")
    holdout = c.get("design", {}).get("type") == "national_holdout"
    plan_geos = {cell["id"]: set(cell["geo_ids"]) for cell in c["cells"]}
    present = set(panel.geos)
    missing_cells = sorted(set().union(*plan_geos.values()) - present)
    if holdout:
        # The campaign runs nearly everywhere; a market with no sales rows simply drops out of its total (§13.4)
        plan_geos = {k: g & present for k, g in plan_geos.items()}
    elif missing_cells:
        errors.append(f"{len(missing_cells)} test markets have no sales rows: {', '.join(missing_cells[:8])}.")
    if holdout and not set(c["control"]["geo_ids"]) & present:
        errors.append("A national holdout plan needs holdout markets with sales rows.")
    if errors:
        return {"ok": False, "errors": errors}

    end = min(pd.Timestamp(d["cooldown_end"]), last)
    interim = end < pd.Timestamp(d["cooldown_end"]) or pd.Timestamp(today) < pd.Timestamp(d["cooldown_end"])
    pre_cols = np.arange(panel.day(d["pre_start"]), panel.day(d["pre_end"]) + 1)
    post_cols = np.arange(panel.day(d["test_start"]), panel.day(end) + 1)
    test_days = min(len(post_cols), (pd.Timestamp(d["test_end"]) - pd.Timestamp(d["test_start"])).days + 1)
    control = [g for g in c["control"]["geo_ids"] if g in present]
    missing_control = sorted(set(c["control"]["geo_ids"]) - present)
    kpis = [k for k in [c["kpi"]["primary"], *c["kpi"].get("secondary", [])] if k in panel.kpis]
    spend_by = spend.spend_by_cell() if spend else {}
    # The planned MDE is locked in the commitment (plans from FOSIT 0.1.0 have it only in the unhashed appendix)
    by_label = {cell["label"]: cell["id"] for cell in c["cells"]}
    planned_mde = (c["decision"].get("planned_mde_lift") or
                   {by_label[m["label"]]: m["mde"] for m in (appendix or {}).get("mde", []) if m.get("mde") and m.get("label") in by_label})

    # §9.3: plans can lock the pre-period fit check on weekly totals (small advertisers); older plans are day by day
    fit_period = 7 if thresholds_period(c) == "week" else 1
    # §5.6: plans that lock placebo calibration get conformal ranges checked against placebo cells
    n_placebos = int((method.get("placebo_calibration") or {}).get("n", 0))
    cells_out, work = [], {}
    total_steps = len(kpis) * len(c["cells"]) * 2
    step = 0
    for ki, kpi in enumerate(kpis):
        for ci, cell in enumerate(c["cells"]):
            if holdout:
                est = estimate_holdout(panel, kpi, control, sorted(plan_geos[cell["id"]]), pre_cols, post_cols,
                                       method.get("test_statistic", "abs_sum"), levels, fixed_effects, perms, min_nonzero)
                series = est.series
            else:
                series = cell_series(panel, kpi, sorted(plan_geos[cell["id"]]), control, pre_cols, post_cols, min_nonzero)
                est = estimate(series, method.get("test_statistic", "abs_sum"), levels, fixed_effects, kpi=kpi, perms=perms)
            cal = None
            if n_placebos:
                target = est.index if holdout else est
                z = placebo_errors(panel, kpi, len(control) if holdout else len(plan_geos[cell["id"]]),
                                   sorted(plan_geos[cell["id"]]) if holdout else control, pre_cols, post_cols,
                                   holdout=holdout, n=n_placebos, seed=[int(method.get("seed", 0)), ci, ki],
                                   fixed_effects=fixed_effects, min_nonzero_share=min_nonzero)
                cal = calibrate(target, z, levels)
            work[(kpi, cell["id"])] = {"id": cell["id"], "series": series, "est": est, "spend": spend_by.get(cell["id"]),
                                       "placebo": cal.to_dict() if cal else ({"n": 0} if n_placebos else None)}
            step += 1
            if progress:
                progress({"stage": "estimate", "done": step, "total": total_steps})

    budgets = {cell["id"]: float(cell["budget"]) for cell in c["cells"]}
    thresholds = c["thresholds"]
    for cell in c["cells"]:
        cid = cell["id"]
        kpi_out = {}
        fit_checks = []
        for kpi in kpis:
            w = work[(kpi, cid)]
            est = w["est"]
            m = business_metrics(est, kpi, w["spend"], levels)
            limit = thresholds["pre_fit_nrmse_max"].get(cid, {}).get(kpi)
            m["pre_fit_nrmse"] = est.pre_fit(fit_period)
            m["pre_fit_period"] = "week" if fit_period == 7 else "day"
            m["pre_fit_limit"] = limit
            m["pre_fit_ok"] = True if limit is None else m["pre_fit_nrmse"] <= limit
            fit_checks.append({"kpi": kpi, "nrmse": m["pre_fit_nrmse"], "limit": limit, "ok": m["pre_fit_ok"],
                               "period": m["pre_fit_period"]})
            m["series"] = {"dates": [x.strftime("%Y-%m-%d") for x in est.dates], **est.chart(),
                           "n_pre": est.n_pre, "test_days": test_days}
            top = sorted(est.weights.items(), key=lambda kv: -abs(kv[1]))[:12]
            m["placebo"] = w["placebo"]
            m["under_the_hood"] = {"lambda": est.lam, "top_weights": [{"geo_id": g, "weight": wt} for g, wt in top],
                                   "negative_weight_sum": float(sum(v for v in est.weights.values() if v < 0)),
                                   "donors": len(est.weights), "dropped_donors": est.dropped_donors,
                                   "tests_evaluated": len(est.evaluated)}
            kpi_out[kpi] = m
        primary = c["kpi"]["primary"]
        pest = work[(primary, cid)]["est"]
        spend_k = work[(primary, cid)]["spend"]
        dec = c["decision"]
        meaningful, basis_note = None, ""
        test_cf = pest.test_counterfactual(test_days)
        if dec["meaningful_effect_basis"] == "target_icpa" and primary == "orders" and dec.get("target_icpa") and spend_k:
            meaningful = spend_k / float(dec["target_icpa"])
            basis_note = f"orders needed to reach the target iCPA of {dec['target_icpa']}"
        elif dec["meaningful_effect_basis"] == "breakeven_iroas" and primary == "revenue" and dec.get("breakeven_iroas") and spend_k:
            meaningful = spend_k * float(dec["breakeven_iroas"])
            basis_note = f"revenue needed to reach the break-even iROAS of {dec['breakeven_iroas']}"
        elif planned_mde.get(cid):
            meaningful = float(planned_mde[cid]) * test_cf
            basis_note = f"the planned minimum detectable lift of {float(planned_mde[cid]):.1%}"
        v, why = verdict(pest, decision_level, meaningful, all(f["ok"] for f in fit_checks if f["kpi"] == primary))
        leak = leakage(spend, cid, plan_geos, set(c["control"]["geo_ids"]), set(c["excluded"]["geo_ids"])) if spend else None
        cells_out.append({"id": cid, "label": cell["label"], "budget": budgets[cid], "spend": spend_k, "n_geos": len(plan_geos[cid]),
                          "kpis": kpi_out, "verdict": v, "verdict_reason": why,
                          "meaningful_effect": meaningful, "meaningful_basis": basis_note,
                          "fit_checks": fit_checks, "leakage": leak})

    h2h = []
    if len(c["cells"]) > 1:
        for kpi in kpis:
            grids = {}
            for cell in c["cells"]:
                w = work[(kpi, cell["id"])]
                w["grid"] = _grid_for(w["series"], w["est"].index if holdout else w["est"], perms, fixed_effects)
                grids[cell["id"]] = w
                step += 1
                if progress:
                    progress({"stage": "head_to_head", "done": step, "total": total_steps})
            for a, b in combinations(c["cells"], 2):
                h = head_to_head(grids[a["id"]], grids[b["id"]], kpi, levels, decision_level)
                h["a_label"], h["b_label"] = a["label"], b["label"]
                h2h.append(h)

    checks = _checks(c, cells_out, spend, budgets, interim, end, today, missing_control, holdout,
                     missing_cells if holdout else [])
    result = {
        "ok": True, "interim": interim, "design": "national_holdout" if holdout else "geo_cells",
        "window": {"pre_start": d["pre_start"], "pre_end": d["pre_end"], "start": d["test_start"],
                   "end": end.strftime("%Y-%m-%d"), "planned_end": d["cooldown_end"], "days": len(post_cols), "test_days": test_days},
        "alpha": alpha, "decision_level": decision_level, "levels": list(levels),
        "permutations": {"kind": perms.kind, "n": perms.n if perms.kind == "iid" else len(pre_cols) + len(post_cols)},
        "primary_kpi": c["kpi"]["primary"], "primary_metric": c["decision"]["primary_metric"],
        "cells": cells_out, "head_to_head": h2h, "checks": checks,
    }
    result["csv"] = results_csv(result, plan_hash)
    return _clean(result)


def _checks(c, cells_out, spend, budgets, interim, end, today, missing_control, holdout=False, missing_campaign=()) -> list[dict]:
    """§11 data-based checks. Plan match and external shocks are added by the UI (they need the user)."""
    th = c["thresholds"]
    out = []
    fit_bad = [f"{cell['label']} ({f['kpi']}{', on weekly totals' if f.get('period') == 'week' else ''}: {f['nrmse']:.1%} > {f['limit']:.1%})"
               for cell in cells_out for f in cell["fit_checks"] if not f["ok"]]
    ok_text = ("The holdout's twin tracked the holdout markets within the plan's limit before the test." if holdout
               else "Every cell's twin tracked its markets within the plan's limits before the test.")
    out.append({"id": "pre_fit", "title": "Pre-period fit", "status": "warn" if fit_bad else "pass", "blocking": True,
                "detail": ("Twin fit is above the plan's limit for " + "; ".join(fit_bad) + ". Affected cells are reported as inconclusive.")
                if fit_bad else ok_text})
    if spend is None:
        out.append({"id": "leakage", "title": "Geo leakage", "status": "warn", "blocking": False,
                    "detail": "No spend & delivery file loaded, so leakage can't be checked."})
        out.append({"id": "spend_balance", "title": "Spend balance", "status": "warn", "blocking": False,
                    "detail": "No spend & delivery file loaded: iCPA and iROAS can't be computed."})
    else:
        warn_share = float(th["leakage_warn_share"])
        lk = []
        for cell in cells_out:
            l = cell["leakage"]
            if l and (l["leak_share"] > warn_share or l["unverifiable_share"] > warn_share):
                lk.append(f"{cell['label']}: {l['leak_share']:.1%} outside its markets, {l['unverifiable_share']:.1%} unverifiable")
        if holdout:
            detail = (("; ".join(lk) + ". Ads in the holdout markets push the measured effect toward zero.") if lk
                      else f"At most {warn_share:.0%} of impressions landed in the holdout markets or couldn't be placed.")
        else:
            detail = (("; ".join(lk) + ". Ads in control markets push lift toward zero; ads in another cell's markets blur the comparison.")
                      if lk else f"Every cell delivered at most {warn_share:.0%} of impressions outside its own markets.")
        out.append({"id": "leakage", "title": "Geo leakage", "status": "warn" if lk else "pass", "blocking": False, "detail": detail})
        total_budget = sum(budgets.values())
        total_spend = sum((cell["spend"] or 0) for cell in cells_out)
        tol = float(th["spend_share_tolerance_pp"]) / 100
        problems = []
        for cell in cells_out:
            s = cell["spend"] or 0
            planned = budgets[cell["id"]] / total_budget if total_budget else 0
            real = s / total_spend if total_spend else 0
            if len(cells_out) > 1 and abs(real - planned) > tol:
                problems.append(f"{cell['label']} got {real:.0%} of spend vs {planned:.0%} planned")
            if s < float(th["min_budget_delivery"]) * budgets[cell["id"]]:
                problems.append(f"{cell['label']} spent {s:,.0f} of its {budgets[cell['id']]:,.0f} budget")
        out.append({"id": "spend_balance", "title": "Spend balance", "status": "warn" if problems else "pass", "blocking": False,
                    "detail": ("; ".join(problems) + ". iCPA and iROAS use actual spend, so they stay correct.") if problems
                    else "Spend matched the planned split and budgets."})
    out.append({"id": "timing", "title": "Timing", "status": "warn" if interim else "pass", "blocking": False,
                "detail": (f"Read before the planned end ({c['dates']['cooldown_end']}): data runs to {end:%Y-%m-%d}. This is an INTERIM result."
                           if interim else "Read after the test and cooldown ended, with data through the planned end.")})
    if missing_control:
        out.append({"id": "control_coverage", "title": "Holdout markets" if holdout else "Control markets", "status": "warn",
                    "blocking": False,
                    "detail": (f"{len(missing_control)} holdout markets have no sales rows and were left out of the holdout."
                               if holdout else f"{len(missing_control)} control markets have no sales rows and were left out of the twins.")})
    if missing_campaign:
        out.append({"id": "campaign_coverage", "title": "Campaign markets", "status": "warn", "blocking": False,
                    "detail": f"{len(missing_campaign)} campaign markets have no sales rows, so their sales (and any lift there) aren't counted."})
    return out


def results_csv(result: dict, plan_hash: str) -> str:
    """Long-format results file (schema/results.table.json)."""
    rows = []
    lv90, lv95 = "0.9", "0.95"

    def add(scope, cid, label, kpi, metric, est, ivs=None, primary=False, verdict="", note="", ref=""):
        i90 = (ivs or {}).get(lv90) or [None, None]
        i95 = (ivs or {}).get(lv95) or [None, None]
        rows.append({"plan_hash": plan_hash, "scope": scope, "cell_id": cid, "cell_label": label, "kpi": kpi, "metric": metric,
                     "estimate": est, "ci90_low": i90[0], "ci90_high": i90[1], "ci95_low": i95[0], "ci95_high": i95[1],
                     "primary": primary, "verdict": verdict, "note": note, "method_ref": ref})

    for cell in result["cells"]:
        for kpi, m in cell["kpis"].items():
            iv = {lv: x for lv, x in m["intervals"].items()}
            pick = lambda key: {lv: v.get(key) for lv, v in iv.items()}
            is_primary = kpi == result["primary_kpi"]
            add("cell", cell["id"], cell["label"], kpi, "observed", m["observed"], ref="#6-business-metrics")
            add("cell", cell["id"], cell["label"], kpi, "counterfactual", m["counterfactual"], ref="#6-business-metrics")
            add("cell", cell["id"], cell["label"], kpi, "incremental", m["incremental"], pick("incremental"),
                verdict=cell["verdict"] if is_primary else "", primary=is_primary and result["primary_metric"] == "cell_lift",
                ref="#6-business-metrics")
            add("cell", cell["id"], cell["label"], kpi, "lift_pct", m["lift"], pick("lift"), ref="#6-business-metrics")
            add("cell", cell["id"], cell["label"], kpi, "p_value", m["p_value"], ref="#51-testing-a-hypothesized-effect")
            add("cell", cell["id"], cell["label"], kpi, "pre_fit_nrmse", m["pre_fit_nrmse"], ref="#45-pre-period-fit")
            if m.get("spend"):
                add("cell", cell["id"], cell["label"], kpi, "spend", m["spend"], ref="#6-business-metrics")
                add("cell", cell["id"], cell["label"], kpi, "incremental_per_1000", m.get("per_1000"), pick("per_1000"), ref="#6-business-metrics")
                if kpi == "orders":
                    add("cell", cell["id"], cell["label"], kpi, "icpa", m.get("icpa"), pick("icpa"),
                        note="" if (iv.get(lv90) or {}).get("icpa", [None, None])[1] is not None else "upper bound unbounded",
                        ref="#6-business-metrics")
                else:
                    add("cell", cell["id"], cell["label"], kpi, "iroas", m.get("iroas"), pick("iroas"), ref="#6-business-metrics")
    for h in result["head_to_head"]:
        for name, m in h["metrics"].items():
            add("head_to_head", f"{h['a']}|{h['b']}", f"{h['a_label']} vs {h['b_label']}", h["kpi"], name, m["estimate"],
                m["intervals"], primary=name == result["primary_metric"],
                verdict="" if m["distinguishable"] is None else ("distinguishable" if m["distinguishable"] else "not_distinguishable"),
                note=m["note"], ref="#7-head-to-head")
    buf = io.StringIO()
    pd.DataFrame(rows).to_csv(buf, index=False)
    return buf.getvalue()


def _clean(obj):
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return f if math.isfinite(f) else None
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj
