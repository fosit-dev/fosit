"""JSON-in / JSON-out entry points for the web worker (Pyodide).

Everything here is a thin wrapper around the statistical modules; it holds the
loaded panel between calls so large data crosses the JS/Python boundary once.
All inputs and outputs are plain dicts/lists/numbers/strings.
"""

from __future__ import annotations

import csv
import math
from importlib import resources

import numpy as np

from . import __version__, ascm, conformal, orders, power, selection, synthetic
from .panel import Panel, load_kpi_history

_state: dict = {}


def _clean(obj):
    """Make numpy scalars / non-finite floats JSON-safe (inf/nan -> None)."""
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return f if math.isfinite(f) else None
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def version() -> dict:
    return {"fosit_core": __version__, "numpy": np.__version__}


def geo_attributes(unit: str) -> list[dict]:
    """Shipped attributes for 'cbsa' or 'state' (see core/fosit/geo_data/README.md)."""
    name = {"cbsa": "cbsa_attributes.csv", "state": "state_attributes.csv"}[unit]
    text = resources.files("fosit").joinpath("geo_data", name).read_text(encoding="utf-8")
    rows = list(csv.DictReader(text.splitlines()))
    for r in rows:
        r["population"] = int(r["population"]) if r.get("population") else None
        r["treatment_eligible"] = r.get("treatment_eligible", "true") == "true"
    return rows


def load_history(csv_text: str, geo_unit: str = "custom") -> dict:
    """Validate KPI history (SCHEMA.md §1). Keeps the panel for later calls."""
    valid = None
    attrs = []
    if geo_unit in ("cbsa", "state"):
        attrs = geo_attributes(geo_unit)
        valid = {r["geo_id"] for r in attrs}
    panel, issues = load_kpi_history(csv_text, valid)
    _state["panel"] = panel
    _state["attributes"] = {r["geo_id"]: r for r in attrs}
    out = {"ok": panel is not None, "summary": None, "geos": [], "issues": [i.to_dict() for i in issues]}
    if panel is not None:
        kpi = "orders" if "orders" in panel.kpis else "revenue"
        mat = panel.kpis[kpi]
        totals = mat.sum(axis=1)
        share = totals / totals.sum() if totals.sum() > 0 else totals
        names = {g: a.get("geo_name", g) for g, a in _state["attributes"].items()}
        out["summary"] = {**panel.summary(), "daily_totals": mat.sum(axis=0).round(2).tolist(), "chart_kpi": kpi}
        out["geos"] = sorted(({"geo_id": g, "name": names.get(g, g), "share": float(sh)}
                              for g, sh in zip(panel.geos, share)), key=lambda r: -r["share"])
    return _clean(out)


def sample_history(end: str, seed: int = 2026) -> str:
    """CSV text of clearly-synthetic sample data on real CBSA codes, ending on `end` (YYYY-MM-DD)."""
    return synthetic.sample_cbsa_history(geo_attributes("cbsa"), end, seed=seed).to_csv(index=False)


def aggregate_orders(csv_text: str, geo_unit: str, mapping_text: str | None = None) -> dict:
    """Order-level export -> KPI-history CSV text (SCHEMA.md §2), for load_history."""
    if mapping_text:
        zip_map, issues = orders.user_zip_map(mapping_text)
        if zip_map is None:
            return _clean({"ok": False, "csv": None, "issues": [i.to_dict() for i in issues]})
    else:
        zip_map = orders.shipped_zip_map(geo_unit)
    long, issues = orders.aggregate_orders(csv_text, zip_map)
    return _clean({"ok": long is not None, "csv": long.to_csv(index=False) if long is not None else None,
                   "issues": [i.to_dict() for i in issues]})


def design_chart(cells: list, control: list, kpi: str = "orders", pre_days: int = 84, holdout_days: int = 28) -> dict:
    """Each cell's average daily KPI vs its twin over the planning window (§9.3 holdout fit), for charts."""
    panel = _panel()
    n = min(pre_days, panel.n_days)
    cols = np.arange(panel.n_days - n, panel.n_days)
    mat = panel.kpis[kpi][:, cols]
    rows_ok = (mat != 0).mean(axis=1) >= 0.5
    donors = [g for g in control if rows_ok[panel.rows([g])[0]]]
    n_fit = n - holdout_days
    out = []
    for cell in cells:
        y1 = mat[panel.rows(cell)].mean(axis=0)
        fit = ascm.fit(y1, mat[panel.rows(donors)], n_fit)
        out.append({"observed": y1.round(3).tolist(), "twin": fit.counterfactual.round(3).tolist()})
    return _clean({"dates": [d.strftime("%Y-%m-%d") for d in panel.dates[cols]], "fit_end": int(n_fit), "cells": out})


def _panel() -> Panel:
    if _state.get("panel") is None:
        raise RuntimeError("Load KPI history first.")
    return _state["panel"]


def find_designs(config: dict, progress=None) -> dict:
    """Market selection (§9) then power simulation (§10) on the best designs.

    config keys (all optional except budgets): n_cells, kpi, pre_days, durations,
    cooldown_days, share_min, share_max, min_control_share, balance_max, fit_max,
    n_candidates, seed, excluded, alpha, statistic, permutations ("moving_block"|"iid"),
    power_target, power_designs (how many designs get a power simulation),
    budgets (list, one per cell).
    """
    panel = _panel()
    attrs = _state.get("attributes", {})
    durations = tuple(int(d) for d in config.get("durations", (21, 28, 42, 56)))
    pop = {g: a["population"] for g, a in attrs.items() if a.get("population")} or config.get("population")
    sel_cfg = selection.SelectionConfig(
        n_cells=int(config.get("n_cells", 2)), kpi=config.get("kpi", "orders"),
        pre_days=min(int(config.get("pre_days", 84)), panel.n_days), test_days=min(durations),
        share_min=float(config.get("share_min", 0.03)), share_max=float(config.get("share_max", 0.15)),
        min_control_share=float(config.get("min_control_share", 0.5)),
        balance_max=float(config.get("balance_max", 0.10)), fit_max=float(config.get("fit_max", 0.10)),
        n_candidates=int(config.get("n_candidates", 2000)), seed=int(config.get("seed", 0)),
        excluded=set(config.get("excluded", [])),
        not_eligible={g for g, a in attrs.items() if not a.get("treatment_eligible", True)},
        population=pop,
    )
    found = selection.MarketSelector(panel, sel_cfg).run(progress)
    designs = found["designs"]
    perms = conformal.Permutations(config.get("permutations", "moving_block"), seed=int(config.get("seed", 0)))
    cooldown = int(config.get("cooldown_days", 7))
    pow_cfg = power.PowerConfig(
        kpi=sel_cfg.kpi, pre_days=sel_cfg.pre_days, durations=durations, adaptive_pre=True,
        cooldown_days=cooldown, alpha=float(config.get("alpha", 0.10)),
        statistic=config.get("statistic", "abs_sum"), permutations=perms,
        power_target=float(config.get("power_target", 0.80)),
    )
    budgets = [float(b) for b in config.get("budgets", [])] or [0.0] * sel_cfg.n_cells
    n_power = int(config.get("power_designs", 5))
    for i, d in enumerate(designs[:n_power]):
        cells = power.PowerSimulator(panel, d.cells, d.control, pow_cfg).run(
            (lambda p, i=i: progress({**p, "design": i + 1, "designs": min(n_power, len(designs))})) if progress else None)
        for c in cells:
            for curve in c["curves"]:
                curve["money"] = power.money(curve, budgets[c["cell_index"]], sel_cfg.kpi)
        d.power = {"cells": cells}

    def rank_key(d: selection.Design):
        if not d.power:
            return (2, math.inf, max(d.fit))
        flagged = any(cv["calibration_flag"] for c in d.power["cells"] for cv in c["curves"])
        primary = [cv for c in d.power["cells"] for cv in c["curves"] if cv["test_days"] == durations[0]]
        worst = max((cv["mde"] if cv["mde"] is not None else math.inf) for cv in primary)
        return (1 if flagged else 0, worst, max(d.fit))

    designs.sort(key=rank_key)
    return _clean({"designs": [d.to_dict() for d in designs], "funnel": found["funnel"],
                   "best_failing": [d.to_dict() for d in found["best_failing"]],
                   "settings": {"selection": {k: v for k, v in vars(sel_cfg).items()
                                              if k not in ("excluded", "not_eligible", "population")},
                                "power": {**{k: v for k, v in vars(pow_cfg).items() if k != "permutations"},
                                          "permutations": vars(perms)}}})
