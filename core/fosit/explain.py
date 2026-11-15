"""Plain-language answers, and the interactive HTML pages for plans and results.

Everything a reader sees first is written here once, so the web app, the agent skill and the HTML file all say the
same thing. The words follow ASD-STE100 (Simplified Technical English) rules: short sentences, active voice, one
instruction per sentence, one word for one meaning ("extra orders", "twin", "range"). See docs/UX_FLOW.md §Writing.
Nothing here computes a statistic: it only words what read.py and the plan already hold.
"""

from __future__ import annotations

import html
import json
import math
from datetime import date, timedelta
from importlib import resources

SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "ILS": "₪", "CAD": "CA$", "AUD": "A$", "JPY": "¥"}
LEVELS = ("brief", "guided", "full")


def day(s: str) -> str:
    """'2026-09-07' -> 'Sep 7, 2026'."""
    d = date.fromisoformat(s)
    return f"{d:%b} {d.day}, {d.year}"


def money(x, cur: str = "USD") -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "–"
    sym = SYMBOLS.get(cur, cur + " ")
    sign = "-" if x < 0 else ""
    return f"{sign}{sym}{abs(x):,.0f}" if abs(x) >= 100 else f"{sign}{sym}{abs(x):,.2f}"


def num(x) -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "–"
    return f"{x:,.0f}"


def amount(kpi: str, x, cur: str) -> str:
    return money(x, cur) if kpi == "revenue" else num(x)


def extra(kpi: str, x, cur: str) -> str:
    """'1,240 extra orders' or '$52,000 of extra revenue'."""
    return f"{money(x, cur)} of extra revenue" if kpi == "revenue" else f"{num(x)} extra orders"


def span(iv, f) -> str:
    if not iv or (iv[0] is None and iv[1] is None):
        return "not defined"
    lo, hi = iv
    if hi is None:
        return f"{f(lo)} or more"
    if lo is None:
        return f"up to {f(hi)}"
    return f"{f(lo)} to {f(hi)}"


# ---------------------------------------------------------------- the answer

def _cell_answer(cell: dict, r: dict, c: dict) -> dict:
    kpi, cur = r["primary_kpi"], c["currency"]
    key = str(r["decision_level"])
    lp = f"{r['decision_level']:.0%}"
    m = cell["kpis"][kpi]
    iv = m["intervals"][key]
    label = cell["label"]
    target = c["decision"].get("target_icpa") if kpi == "orders" else c["decision"].get("breakeven_iroas")
    v = cell["verdict"]
    detail = [f"The {lp} range is {span(iv['incremental'], lambda x: amount(kpi, x, cur))}."]
    action = ""
    if v == "positive":
        headline = f"{label} caused about {extra(kpi, m['incremental'], cur)}."
        if kpi == "orders" and m.get("icpa"):
            detail.append(f"One extra order cost about {money(m['icpa'], cur)} "
                          f"(range {span(iv.get('icpa'), lambda x: money(x, cur))}).")
            hi = (iv.get("icpa") or [None, None])[1]
            lo = (iv.get("icpa") or [None, None])[0]
            if target:
                if hi is not None and hi <= target:
                    action = f"Keep {label}. Even the high end of the cost per extra order is below your target of {money(target, cur)}."
                elif lo is not None and lo > target:
                    action = (f"{label} works, but one extra order costs more than your target of {money(target, cur)}. "
                              "Lower the price or improve the campaign before you spend more.")
                else:
                    action = f"{label} works. The cost per extra order can be above or below your target of {money(target, cur)}."
            else:
                action = f"{label} works. Compare {money(m['icpa'], cur)} per extra order with the value of one order to you."
        elif kpi == "revenue" and m.get("iroas") is not None:
            detail.append(f"Each 1 {cur} of spend brought about {m['iroas']:.2f} {cur} of extra revenue "
                          f"(range {span(iv.get('iroas'), lambda x: f'{x:.2f}')}).")
            lo, hi = iv.get("iroas") or [None, None]
            if not target:
                action = f"{label} works. It pays back if {m['iroas']:.2f} per 1 {cur} is more than your break-even."
            elif lo is not None and lo >= target:
                action = f"Keep {label}. Even the low end of the return is above your break-even of {target:.2f}."
            elif hi is not None and hi < target:
                action = (f"{label} works, but the return is below your break-even of {target:.2f}. "
                          "Lower the price or improve the campaign before you spend more.")
            else:
                action = f"{label} works. The return can be above or below your break-even of {target:.2f}."
        else:
            action = f"{label} works. Add the spend file to see the cost per extra order."
    elif v == "negative":
        headline = f"{label}: sales were lower with the ads."
        action = "Check the data and where the ads ran before you act on this result. Ads seldom reduce sales."
    elif v == "no_detectable_lift":
        headline = f"{label} did not cause enough extra sales to pay off."
        if cell.get("meaningful_effect"):
            detail.append(f"The test rules out {amount(kpi, cell['meaningful_effect'], cur)} or more, "
                          f"the amount needed to pay off.")
        action = f"Do not spend more on {label} in this form. Change the offer, the creative or the audience, or stop it."
    else:
        fit_failed = any(not f["ok"] for f in cell.get("fit_checks", []) if f["kpi"] == kpi)
        if fit_failed:
            headline = f"{label}: the test cannot give an answer."
            detail = ["Before the test, the twin did not follow these markets closely enough."]
            action = "Do not use this result to decide. An analyst can look at the fit chart with you."
        else:
            headline = f"{label}: the test cannot tell yet."
            detail.append("The range includes zero, and also effects large enough to pay off.")
            action = "Do not decide on this result alone. A longer test or a larger budget can give a clear answer."
    return {"id": cell["id"], "label": label, "verdict": v, "headline": headline, "detail": " ".join(detail), "action": action}


def _h2h_answer(h: dict, r: dict, c: dict) -> dict | None:
    key = str(r["decision_level"])
    cur = c["currency"]
    name = r["primary_metric"] if r["primary_metric"] in h["metrics"] else "delta_incremental_per_1000"
    m = h["metrics"].get(name)
    if not m or not m["intervals"].get(key):
        m = h["metrics"].get("delta_incremental_per_1000")
        name = "delta_incremental_per_1000"
    if not m or not m["intervals"].get(key):
        return None
    lo, hi = m["intervals"][key]
    a, b = h["a_label"], h["b_label"]
    lower_is_better = name in ("delta_icpa", "ratio_icpa")
    null = m.get("null", 0.0)
    if m["distinguishable"]:
        a_better = (hi < null) if lower_is_better else (lo > null)
        win, lose = (a, b) if a_better else (b, a)
        what = {"delta_icpa": "a lower cost per extra order", "ratio_icpa": "a lower cost per extra order",
                "delta_iroas": "more extra revenue per $1"}.get(name, "more extra sales per $1,000")
        return {"headline": f"{win} did better than {lose}: {what}.",
                "detail": "The difference is larger than chance can explain.", "winner": win}
    return {"headline": f"The test cannot tell if {a} or {b} is better.",
            "detail": "Their ranges overlap. Do not pick a vendor on this result alone.", "winner": None}


def summary(r: dict, c: dict) -> dict:
    """The answer first: one headline, one detail and one action per cell, plus the vendor comparison."""
    out = {"cells": [_cell_answer(cell, r, c) for cell in r["cells"]], "head_to_head": None, "notes": []}
    pairs = [h for h in r.get("head_to_head", []) if h["kpi"] == r["primary_kpi"]]
    if len(pairs) == 1:
        out["head_to_head"] = _h2h_answer(pairs[0], r, c)
    if r.get("interim"):
        out["notes"].append(f"This is an early read. The test ends on {day(r['window']['planned_end'])}. The numbers can change.")
    return out


# ---------------------------------------------------------------- page data

def design_kind(c: dict) -> str:
    t = c.get("design", {}).get("type", "geo_cells")
    if t == "national_holdout":
        return "split" if len(c["cells"]) > 1 else "holdout"
    return "crossover" if t == "crossover" else "cells"


def _shares(c: dict, appendix: dict | None) -> tuple[list, float | None]:
    d = (appendix or {}).get("design") or {}
    shares = d.get("shares")
    if not shares or len(shares) != len(c["cells"]):
        return [None] * len(c["cells"]), None
    rest = d.get("holdout_share")
    if rest is None:
        rest = max(0.0, 1.0 - sum(shares))
    return shares, rest


def groups(c: dict, appendix: dict | None, names: dict | None) -> list[dict]:
    names = names or {}
    nm = lambda ids: [names.get(g, g) for g in ids]
    shares, rest = _shares(c, appendix)
    kind = design_kind(c)
    out = []
    if kind == "crossover":
        cell = c["cells"][0]
        out.append({"id": cell["id"], "label": "Half A", "role": "half", "share": shares[0], "n": len(cell["geo_ids"]),
                    "markets": nm(cell["geo_ids"]), "budget": cell["budget"]})
        out.append({"id": "control", "label": "Half B", "role": "half", "share": rest, "n": len(c["control"]["geo_ids"]),
                    "markets": nm(c["control"]["geo_ids"])})
        return out
    for k, cell in enumerate(c["cells"]):
        out.append({"id": cell["id"], "label": cell["label"], "role": "ads", "share": shares[k], "n": len(cell["geo_ids"]),
                    "markets": nm(cell["geo_ids"]), "budget": cell["budget"]})
    out.append({"id": "control", "label": "No-ads holdout" if kind in ("holdout", "split") else "Control (no test ads)",
                "role": "holdout" if kind in ("holdout", "split") else "control", "share": rest,
                "n": len(c["control"]["geo_ids"]), "markets": nm(c["control"]["geo_ids"])})
    return out


def schedule_rows(c: dict) -> list[dict]:
    x = c.get("design", {})
    if x.get("type") != "crossover":
        return []
    start = date.fromisoformat(c["dates"]["test_start"])
    L, W = int(x["block_days"]), int(x["washout_days"])
    return [{"block": b + 1, "start": (start + timedelta(days=b * L)).isoformat(),
             "end": (start + timedelta(days=(b + 1) * L - 1)).isoformat(), "on": on, "washout_days": W}
            for b, on in enumerate(x["schedule"])]


def checklist(c: dict) -> list[dict]:
    """Who does what, in imperative sentences (STE: one instruction per sentence)."""
    d = c["dates"]
    kind = design_kind(c)
    you = ["Send the plan file, this page and the fingerprint to every vendor before the test starts.",
           "Get a written answer from every vendor that it can target exactly its markets.",
           "Keep prices, promotions and other media the same in all markets during the test.",
           "Write down each change that happens in only some markets."]
    read = [f"After {day(d['cooldown_end'])}, export daily sales by market from {day(d['pre_start'])} to {day(d['cooldown_end'])}.",
            "Get daily spend and impressions by market from each vendor.",
            "Load the plan, the sales file and the spend file on the Read page."]
    out = [{"who": "You (the advertiser)", "items": you}]
    if kind == "crossover":
        cell = c["cells"][0]
        out.append({"who": "The vendor", "items": [
            f"Run the ads only in the half that the schedule shows, from {day(d['test_start'])} to {day(d['test_end'])}.",
            "Move the ads to the other half on the first day of each block.",
            "Keep the budget per day the same in every block.",
            "After the test, send daily spend and impressions by market."]})
    else:
        for cell in c["cells"]:
            items = [f"Run ads only in your {len(cell['geo_ids'])} markets, from {day(d['test_start'])} to {day(d['test_end'])}.",
                     "Run no ads in other markets.",
                     "After the test, send daily spend and impressions by market."]
            out.append({"who": cell["label"] if len(c["cells"]) > 1 or kind == "cells" else "The vendor", "items": items})
        if kind in ("holdout", "split"):
            out.append({"who": "Everyone", "items": [
                f"Run no CTV in the {len(c['control']['geo_ids'])} held-out markets from {day(d['test_start'])} to {day(d['cooldown_end'])}."]})
    out.append({"who": "When the test ends", "items": read})
    return out


def one_line(c: dict, appendix: dict | None = None) -> str:
    """The plan in two or three short sentences."""
    d = c["dates"]
    kind = design_kind(c)
    labels = [x["label"] for x in c["cells"]]
    who = " and ".join(labels) if len(labels) <= 2 else ", ".join(labels[:-1]) + " and " + labels[-1]
    shares, rest = _shares(c, appendix)
    held = f" ({rest:.0%} of sales)" if rest is not None else ""
    if kind == "crossover":
        weeks = int(c["design"]["block_days"]) // 7
        return (f"Two halves of the country take turns with the ads, every {weeks} weeks, from {day(d['test_start'])} to {day(d['test_end'])}. "
                "Each half has the ads in half of the blocks. FOSIT compares the two halves in each block.")
    if kind == "holdout":
        return (f"{who} runs everywhere except {len(c['control']['geo_ids'])} held-out markets{held}, from {day(d['test_start'])} "
                f"to {day(d['test_end'])}. FOSIT compares the held-out markets with their twin. Read the results after {day(d['cooldown_end'])}.")
    if kind == "split":
        return (f"{who} split the country. {len(c['control']['geo_ids'])} markets{held} get no CTV. The ads run from "
                f"{day(d['test_start'])} to {day(d['test_end'])}. Read the results after {day(d['cooldown_end'])}.")
    return (f"{who} {'each run' if len(labels) > 1 else 'runs'} ads only in {'their own' if len(labels) > 1 else 'its'} markets, "
            f"from {day(d['test_start'])} to {day(d['test_end'])}. {len(c['control']['geo_ids'])} markets{held} get no test ads. "
            f"Read the results after {day(d['cooldown_end'])}.")


def sensitivity(c: dict, appendix: dict | None) -> list[dict]:
    """What the test can see, per cell, from the planning simulation (§10). Not part of the fingerprint."""
    out = []
    planned = c["decision"].get("planned_mde_lift") or {}
    by_label = {m.get("label"): m for m in (appendix or {}).get("mde", [])}
    for cell in c["cells"]:
        m = by_label.get(cell["label"], {})
        out.append({"label": "The campaign" if design_kind(c) == "crossover" else cell["label"], "budget": cell["budget"],
                    "mde": m.get("mde", planned.get(cell["id"])), "detectable_icpa": m.get("detectable_icpa"),
                    "baseline_test_total": m.get("baseline_test_total"), "points": m.get("points") or []})
    return out


def _base(c: dict, kind: str, level: str, names: dict | None) -> dict:
    return {"kind": kind, "level": level if level in LEVELS else "guided", "title": c["test_name"],
            "advertiser": c.get("advertiser_label") or "", "currency": c["currency"], "kpi": c["kpi"]["primary"],
            "design": design_kind(c), "dates": c["dates"], "unit": c["geo"]["unit"]}


def plan_payload(plan: dict, names: dict | None = None, read_url: str | None = None, level: str = "guided") -> dict:
    c = plan["commitment"]
    appendix = plan.get("appendix")
    p = _base(c, "plan", level, names)
    p.update({"fingerprint": plan["hash"]["value"], "one_line": one_line(c, appendix), "groups": groups(c, appendix, names),
              "schedule": schedule_rows(c), "block_days": c.get("design", {}).get("block_days"),
              "washout_days": c.get("design", {}).get("washout_days"), "checklist": checklist(c),
              "sensitivity": sensitivity(c, appendix), "read_url": read_url or "",
              "decision": c["decision"], "method": c["method"], "thresholds": c["thresholds"],
              "ads_before": c.get("design", {}).get("ads_before_test"), "excluded": len(c["excluded"]["geo_ids"]),
              "engine": c["tool"].get("core_sha256", "")})
    return p


def results_payload(plan: dict, result: dict, names: dict | None = None, checks: list | None = None,
                    level: str = "guided", plan_ok: bool | None = None) -> dict:
    """checks: the full honesty-check list as the person saw it (the UI adds plan match and other changes)."""
    c = plan["commitment"]
    p = _base(c, "results", level, names)
    cells = []
    for cell in result["cells"]:
        m = cell["kpis"][result["primary_kpi"]]
        cells.append({"id": cell["id"], "label": cell["label"], "verdict": cell["verdict"], "reason": cell["verdict_reason"],
                      "n": cell["n_geos"], "spend": cell.get("spend"), "budget": cell["budget"],
                      "meaningful": cell.get("meaningful_effect"), "kpis": {
                          k: {kk: v[kk] for kk in ("incremental", "lift", "icpa", "iroas", "per_1000", "p_value", "observed",
                                                   "counterfactual", "pre_fit_nrmse", "pre_fit_limit", "pre_fit_period",
                                                   "intervals", "spend") if kk in v}
                          for k, v in cell["kpis"].items()},
                      "series": m["series"]})
    p.update({"fingerprint": plan["hash"]["value"], "summary": result.get("summary") or summary(result, c),
              "groups": groups(c, plan.get("appendix"), names), "schedule": schedule_rows(c),
              "block_days": c.get("design", {}).get("block_days"), "washout_days": c.get("design", {}).get("washout_days"),
              "interim": result["interim"], "window": result["window"], "decision_level": result["decision_level"],
              "levels": result["levels"], "cells": cells, "head_to_head": result["head_to_head"],
              "checks": checks if checks is not None else result["checks"], "plan_ok": plan_ok,
              "decision": c["decision"], "method": c["method"], "permutations": result.get("permutations"),
              "engine": c["tool"].get("core_sha256", "")})
    return p


def designs_payload(found: dict, labels: list, budgets: list, currency: str, kpi: str, title: str = "Candidate designs",
                    kind: str = "cells", level: str = "guided") -> dict:
    """The planner's top designs, to compare (the skill's `plan` step)."""
    designs = []
    for d in found.get("designs", [])[:5]:
        sens = []
        for k, pc in enumerate((d.get("power") or {}).get("cells", [])):
            sens.append({"label": labels[k] if k < len(labels) else f"Cell {k + 1}", "budget": budgets[k] if k < len(budgets) else None,
                         "curves": [{"test_days": cv["test_days"], "mde": cv.get("mde"),
                                     "detectable_icpa": (cv.get("money") or {}).get("detectable_icpa"),
                                     "baseline_test_total": cv.get("baseline_test_total"), "points": cv.get("points") or []}
                                    for cv in pc["curves"]]})
        designs.append({"shares": d["shares"], "control_share": d.get("control_share"), "n_cells": [len(x) for x in d["cells"]],
                        "n_control": len(d["control"]), "fit": d["fit"], "balance_score": d["balance_score"], "sensitivity": sens})
    return {"kind": "designs", "level": level if level in LEVELS else "guided", "title": title, "currency": currency, "kpi": kpi,
            "design": kind, "labels": labels, "budgets": budgets, "designs": designs, "fit_period": found.get("fit_period"),
            "funnel": found.get("funnel", {})}


# ---------------------------------------------------------------- render

def _clean(obj):
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if hasattr(obj, "item"):          # numpy scalars
        return _clean(obj.item())
    return obj


def render(payload: dict) -> str:
    """One self-contained HTML file: no network requests, works offline, prints cleanly."""
    text = resources.files("fosit").joinpath("templates", "page.html").read_text(encoding="utf-8")
    data = json.dumps(_clean(payload), separators=(",", ":"), ensure_ascii=False)
    data = data.replace("</", "<\\/").replace("<!--", "<\\!--")
    title = html.escape(f"{payload['title']} · FOSIT")
    return text.replace("__FOSIT_TITLE__", title).replace("/*__FOSIT_DATA__*/null", data)
