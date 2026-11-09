#!/usr/bin/env python3
"""FOSIT from the command line: plan, lock, verify and read geo-lift tests with the same engine as the web app.

    python fosit_cli.py setup
    python fosit_cli.py check   SALES.csv --unit state
    python fosit_cli.py orders  ORDERS.csv --unit cbsa --out sales.csv [--mapping zip_to_market.csv]
    python fosit_cli.py sample  --unit state --out sample.csv [--end 2026-11-01]
    python fosit_cli.py plan    SALES.csv --unit state --design cells|holdout|split [...] --out plan_work/
    python fosit_cli.py lock    plan_work/ --choose 1 --weeks 4 --name "Q1 CTV test" --confirm-targeting [...]
    python fosit_cli.py verify  PLAN.fosit-plan.json [--fingerprint HASH]
    python fosit_cli.py read    PLAN.fosit-plan.json --sales SALES.csv [--spend SPEND.csv] --out results/ [...]

Every command prints a short Markdown summary (aggregates only, never raw rows) and writes its
full output to files. The engine is FOSIT's own Python core (github.com/fosit-dev/fosit), pinned
below so results are reproducible; the plan records the exact code fingerprint it ran with.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

FOSIT_REPO = "https://github.com/fosit-dev/fosit"
FOSIT_REF = os.environ.get("FOSIT_REF", "922eca4")          # pinned engine version (a commit or tag)
HOME = Path(os.environ.get("FOSIT_ENV", Path.home() / ".fosit"))
VENV = HOME / f"venv-{FOSIT_REF}"


# ---------------------------------------------------------------------------- engine

def _venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _local_core() -> Path | None:
    """A FOSIT checkout to use instead of the pinned install (FOSIT_HOME, or the current repo)."""
    for root in filter(None, [os.environ.get("FOSIT_HOME"), os.getcwd()]):
        core = Path(root) / "core"
        if (core / "fosit" / "api.py").exists():
            return core
    return None


def _engine_ready() -> bool:
    try:
        import fosit  # noqa: F401
        import numpy, pandas, scipy  # noqa: F401,E401
        return True
    except ImportError:
        return False


def _find_python() -> list[str] | None:
    """A Python >= 3.12 to build the engine's environment with (uv can fetch one if none is installed)."""
    if sys.version_info >= (3, 12):
        return [sys.executable]
    if shutil.which("uv"):
        return ["uv"]
    for name in ("python3.14", "python3.13", "python3.12", "python3", "python"):
        exe = shutil.which(name)
        if not exe:
            continue
        out = subprocess.run([exe, "-c", "import sys; print(sys.version_info >= (3, 12))"], capture_output=True, text=True)
        if out.stdout.strip() == "True":
            return [exe]
    return None


def ensure_engine() -> None:
    """Import the engine, installing it into ~/.fosit on first use and re-running this script there."""
    local = _local_core()
    if local:
        sys.path.insert(0, str(local))
    if _engine_ready():
        return
    py = _venv_python()
    if not py.exists():
        maker = _find_python()
        if maker is None:
            sys.exit("FOSIT needs Python 3.12 or newer. Install it (or `uv`, which fetches one), then run this again.")
        HOME.mkdir(parents=True, exist_ok=True)
        print(f"Setting up FOSIT's engine ({FOSIT_REF}) in {VENV} (one time)...", file=sys.stderr)
        pkg = f"fosit-core @ git+{FOSIT_REPO}@{FOSIT_REF}#subdirectory=core"
        if maker == ["uv"]:
            subprocess.run(["uv", "venv", "--python", "3.12", str(VENV)], check=True, stdout=sys.stderr)
            subprocess.run(["uv", "pip", "install", "--python", str(py), pkg], check=True, stdout=sys.stderr)
        else:
            subprocess.run([*maker, "-m", "venv", str(VENV)], check=True, stdout=sys.stderr)
            subprocess.run([str(py), "-m", "pip", "install", "--quiet", pkg], check=True, stdout=sys.stderr)
    if Path(sys.prefix).resolve() == VENV.resolve():   # already inside the engine's environment (its python is often a symlink)
        sys.exit("The FOSIT environment exists but the engine won't import. Delete it and run `setup` again: " + str(VENV))
    os.execv(str(py), [str(py), *sys.argv])


def core_sha256() -> str:
    """Fingerprint of the engine's code: the same reproducible zip the web app publishes as fosit-core.json."""
    import fosit
    pkg = Path(fosit.__file__).parent
    buf = io.BytesIO()
    files = sorted((p, "fosit/" + p.relative_to(pkg).as_posix()) for p in pkg.rglob("*")
                   if p.is_file() and "__pycache__" not in p.parts and p.suffix in (".py", ".csv", ".json", ".md"))
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p, arc in sorted(files, key=lambda x: x[1]):
            info = zipfile.ZipInfo(arc, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, p.read_bytes())
    return hashlib.sha256(buf.getvalue()).hexdigest()


# ---------------------------------------------------------------------------- helpers

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def plan_hash(commitment: dict) -> str:
    """SHA-256 of the RFC 8785 canonical commitment (docs/PREREGISTRATION.md: this form equals RFC 8785 for FOSIT plans)."""
    return sha256_bytes(json.dumps(commitment, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())


def rnd(x: float, digits: int) -> float:
    """Schema-safe rounding: numbers in a commitment are integers or decimals with |x| in [0.0001, 1e15)."""
    r = round(float(x), digits)
    if r == int(r):
        return int(r)
    return r if abs(r) >= 1e-4 else 0.0001 * (1 if r > 0 else -1)


def pct(x, d=1):
    return "–" if x is None else f"{x * 100:.{d}f}%"


def money(x, cur="USD"):
    if x is None:
        return "–"
    sym = {"USD": "$", "EUR": "€", "GBP": "£", "CAD": "CA$", "AUD": "A$"}.get(cur, cur + " ")
    return f"{sym}{x:,.0f}" if abs(x) >= 100 else f"{sym}{x:,.2f}"


def num(x):
    return "–" if x is None else f"{x:,.0f}"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def issues_md(issues: list[dict]) -> str:
    if not issues:
        return "No issues found.\n"
    out = []
    for i in issues:
        mark = "ERROR" if i["severity"] == "error" else "warning"
        out.append(f"- **{mark}** `{i['code']}`: {i['message']}")
    return "\n".join(out) + "\n"


def load_sales(path: str, unit: str) -> dict:
    from fosit import api
    text = Path(path).read_text(encoding="utf-8-sig")
    out = api.load_history(text, unit)
    out["_sha256"] = sha256_bytes(Path(path).read_bytes())
    out["_rows"] = max(0, len(text.rstrip().splitlines()) - 1)
    return out


MAPPING_NAMES = {
    "cbsa": "Census 2020 ZCTA-county + OMB July 2023 CBSA delineation (FOSIT geo_data)",
    "state": "Census 2020 ZCTA-county relationship, by state (FOSIT geo_data)",
}


# ---------------------------------------------------------------------------- commands

def cmd_setup(a) -> None:
    import fosit, numpy
    print(f"FOSIT engine {fosit.__version__} (ref {FOSIT_REF}), numpy {numpy.__version__}, code fingerprint {core_sha256()[:16]}…")
    print(f"Engine location: {Path(fosit.__file__).parent}")


def cmd_check(a) -> None:
    out = load_sales(a.sales, a.unit)
    print(f"## Sales file check: {Path(a.sales).name}\n")
    if out["summary"]:
        s = out["summary"]
        print(f"- {s['days']} days ({s['weeks']} weeks), {s['first_date']} to {s['last_date']}")
        print(f"- {s['geos']} markets ({a.unit}); KPIs: {', '.join(s['kpis'])}")
        top = ", ".join(f"{g['name']} {pct(g['share'])}" for g in out["geos"][:5])
        print(f"- Largest markets by share of sales: {top}")
        weeks = s["days"] / 7
        print(f"- History: {'enough (12+ weeks)' if weeks >= 12 else 'short: under 12 weeks widens every range' if weeks >= 8 else 'too short: under 8 weeks, plans are unreliable'}")
    print("\n### Issues\n")
    print(issues_md(out["issues"]))
    print("Result:", "OK" if out["ok"] else "NOT USABLE until the errors above are fixed")


def cmd_orders(a) -> None:
    from fosit import api
    mapping = Path(a.mapping).read_text(encoding="utf-8-sig") if a.mapping else None
    out = api.aggregate_orders(Path(a.orders).read_text(encoding="utf-8-sig"), a.unit, mapping)
    print(f"## Order export → daily sales by market ({a.unit})\n")
    print(issues_md(out["issues"]))
    if out["ok"]:
        write(Path(a.out), out["csv"])
        print(f"Wrote {a.out}. Next: `check` it, then `plan`.")


def cmd_sample(a) -> None:
    from fosit import api, synthetic
    end = a.end or (date.today() - timedelta(days=1)).isoformat()
    if a.unit == "state":
        df = synthetic.sample_state_history(api.geo_attributes("state"), end, n_days=182, seed=a.seed)
        text = df.to_csv(index=False)
    else:
        text = api.sample_history(end, seed=a.seed)
    write(Path(a.out), text)
    print(f"Wrote synthetic sample data ({a.unit}, 26 weeks to {end}) to {a.out}. It is clearly fake: use it to try FOSIT, never as real results.")


def _design_cfg(a, summary: dict) -> dict:
    holdout = a.design in ("holdout", "split")
    n_cells = 1 if a.design == "holdout" else (a.cells or 2)
    labels = [x.strip() for x in a.labels.split(",")] if a.labels else (
        ["Campaign"] if a.design == "holdout" else [f"Cell {i + 1}" for i in range(n_cells)])
    if len(labels) != n_cells:
        sys.exit(f"--labels has {len(labels)} names but the design has {n_cells} cells.")
    split = [float(x) for x in a.split.split(",")] if a.split else [100 / n_cells] * n_cells
    if len(split) != n_cells or abs(sum(split) - 100) > 0.01:
        sys.exit("--split must give one percentage per cell, adding up to 100.")
    budgets = [round(a.budget * p / 100, 2) for p in split]
    pre_days = min(a.pre_weeks * 7, summary["days"])
    durations = sorted({int(w) * 7 for w in a.weeks.split(",")})
    excluded = {}
    for e in a.exclude or []:
        gid, _, reason = e.partition(":")
        excluded[gid.strip()] = reason.strip()
    defaults = {"cells": (0.03, 0.15), "holdout": (0.10, 0.20), "split": (0.15, 0.25)}[a.design]
    return {
        "design": "national_holdout" if holdout else "geo_cells", "n_cells": n_cells, "kpi": a.kpi,
        "pre_days": pre_days, "durations": durations, "cooldown_days": a.cooldown,
        "share_min": a.share_min if a.share_min is not None else defaults[0],
        "share_max": a.share_max if a.share_max is not None else defaults[1],
        "excluded": list(excluded), "seed": a.seed, "permutations": "moving_block", "budgets": budgets, "alpha": 0.1,
        "fit_period": a.fit_period,
        "_labels": labels, "_excluded": excluded, "_kind": a.design,
    }


def cmd_plan(a) -> None:
    from fosit import api
    if a.design == "cells" and (a.cells or 2) > 6:
        sys.exit("At most 6 cells.")
    if a.design == "split" and not 2 <= (a.cells or 2) <= 4:
        sys.exit("A vendor split has 2-4 vendors.")
    loaded = load_sales(a.sales, a.unit)
    if not loaded["ok"]:
        print(issues_md(loaded["issues"]))
        sys.exit("The sales file has errors; run `check` and fix them first.")
    s = loaded["summary"]
    if a.kpi not in s["kpis"]:
        sys.exit(f"The sales file has no {a.kpi} column.")
    cfg = _design_cfg(a, s)
    call = {k: v for k, v in cfg.items() if not k.startswith("_")}
    print(f"Searching designs ({cfg['_kind']}, {cfg['n_cells']} cell(s), {len(s and loaded['geos'])} markets); this can take a few minutes...", file=sys.stderr)
    found = api.find_designs(call)
    out = Path(a.out)
    names = {g["geo_id"]: g["name"] for g in loaded["geos"]}
    work = {"fosit_ref": FOSIT_REF, "sales_file": str(Path(a.sales).resolve()), "unit": a.unit, "currency": a.currency,
            "test_start": a.test_start, "labels": cfg["_labels"], "budgets": cfg["budgets"], "excluded": cfg["_excluded"],
            "config": call, "kind": cfg["_kind"], "kpis": s["kpis"], "names": names,
            "fingerprint": {"kpi_history_sha256": loaded["_sha256"], "rows": loaded["_rows"], "geos": s["geos"],
                            "first_date": s["first_date"], "last_date": s["last_date"]},
            "result": found}
    write(out / "designs.json", json.dumps(work, indent=1))
    lines = [f"# Candidate designs ({cfg['_kind']})", "",
             f"Searched {found['funnel'].get('generated')} random candidates → {found['funnel'].get('passed_share_and_balance')} fair → "
             f"{found['funnel'].get('passed_fit')} fit well"
             f"{' (fit judged on weekly totals: sales are small enough that day-to-day chance would swamp a daily score)' if found.get('fit_period') == 'week' else ''}. Budget {money(a.budget, a.currency)} ({', '.join(f'{l} {money(b, a.currency)}' for l, b in zip(cfg['_labels'], cfg['budgets']))}).", ""]
    if not found["designs"]:
        best = found["best_failing"][0]["fit"] if found["best_failing"] else None
        lines += ["**No design passed every check.** " + (f"The closest had a fit error of {pct(max(best))} (limit 10%). " if best else "") +
                  ("Try a wider holdout share, " if cfg["_kind"] != "cells" else "Try bigger cells (--share-max), ") +
                  "more history, or fewer exclusions."]
    for i, d in enumerate(found["designs"][:a.show]):
        lines.append(f"## Design {i + 1}{' (best)' if i == 0 else ''}")
        held = cfg["_kind"] != "cells"
        lines.append(f"- {'Held out' if held else 'Control'}: {len(d['control'])} markets, {pct(d['control_share'])} of sales"
                     + (" (no ads)" if held else ""))
        for c, cell in enumerate(d["cells"]):
            lines.append(f"- {cfg['_labels'][c]}: {len(cell)} markets, {pct(d['shares'][c])} of sales; fit error {pct(d['fit'][c])}")
        lines.append(f"- Balance gap {pct(d['balance_score'])} ({', '.join(f'{k} {pct(v)}' for k, v in d['balance'].items())})")
        if d["power"]:
            rows = ["| Test length | " + " | ".join(f"{l}: detectable lift / iCPA" for l in cfg["_labels"]) + " |",
                    "|---|" + "---|" * len(cfg["_labels"])]
            for days in cfg["durations"]:
                cells = []
                for c, pc in enumerate(d["power"]["cells"]):
                    cv = next(x for x in pc["curves"] if x["test_days"] == days)
                    icpa = cv.get("money", {}).get("detectable_icpa")
                    flag = " ⚠ fake lifts in past data" if cv.get("calibration_flag") else ""
                    cells.append(f"{pct(cv['mde']) if cv['mde'] else '>50%'} / {money(icpa, a.currency)}{flag}")
                rows.append(f"| {days // 7} weeks | " + " | ".join(cells) + " |")
            lines += ["", *rows]
        else:
            lines.append("- Sensitivity not simulated (only the top designs are).")
        lines.append("")
    lines += ["Detectable lift: the smallest lift this design catches 80% of the time. Detectable iCPA: if a vendor's true "
              "cost per extra order is worse than this, the test probably won't see it.", "",
              f"Next: `lock {out} --choose N --weeks W ...` after every vendor confirms it can target its markets."]
    write(out / "designs.md", "\n".join(lines) + "\n")
    print("\n".join(lines))


def build_commitment(work: dict, d: dict, a) -> tuple[dict, dict]:
    """The plan's hashed commitment, built exactly like the web app's lib/plan.ts::buildCommitment."""
    import fosit
    with open(Path(fosit.__file__).parent / "geo_data" / "SOURCES.json") as f:
        mapping_sha = json.load(f)["outputs"]["zcta_to_geo.csv"]["sha256"]
    unit = work["unit"]
    if unit == "custom":
        mapping_name = "Custom market IDs as provided (no ZIP mapping file)"
        mapping_sha = sha256_bytes("\n".join(sorted(work["names"])).encode())
    else:
        mapping_name = MAPPING_NAMES[unit]
    n = len(d["cells"])
    days = a.weeks * 7
    if days not in work["config"]["durations"]:
        sys.exit(f"{a.weeks} weeks wasn't simulated; choose one of {[x // 7 for x in work['config']['durations']]}.")
    order = list(range(n))
    coin = None
    if a.coin_flip and n > 1:
        import secrets
        order = list(range(n))
        for i in range(n - 1, 0, -1):
            j = secrets.randbelow(i + 1)
            order[i], order[j] = order[j], order[i]
        coin = order
    cells = []
    for k in range(n):
        s = order.index(k)
        cells.append({"id": f"cell_{k + 1}", "label": work["labels"][k], "geo_ids": sorted(d["cells"][s]), "budget": rnd(work["budgets"][k], 2)})
    kpis = [work["config"]["kpi"]] + [k for k in work["kpis"] if k != work["config"]["kpi"]]
    pre_fit = d.get("pre_fit") or [0] * n
    fit_by = {c["id"]: {kpi: rnd(max(min(1.5 * max(d["fit"][order.index(k)], pre_fit[order.index(k)]), 0.15), 0.0001), 4) for kpi in kpis}
              for k, c in enumerate(cells)}
    test_start = date.fromisoformat(work["test_start"])
    pre_end = test_start - timedelta(days=1)
    test_end = test_start + timedelta(days=days - 1)
    curves = [next(cv for cv in pc["curves"] if cv["test_days"] == days) for pc in d["power"]["cells"]] if d["power"] else [None] * n
    mde = [cv["mde"] if cv else None for cv in curves]
    holdout = work["config"]["design"] == "national_holdout"
    c = {
        "tool": {"name": "FOSIT", "version": fosit.__version__, "core_sha256": core_sha256()},
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "test_name": a.name.strip(),
        "currency": work["currency"],
        "geo": {"unit": unit, "mapping_name": mapping_name, "mapping_sha256": mapping_sha},
        "kpi": {"primary": kpis[0], "secondary": kpis[1:], "aggregation": "daily"},
        "dates": {"pre_start": (pre_end - timedelta(days=work["config"]["pre_days"] - 1)).isoformat(), "pre_end": pre_end.isoformat(),
                  "test_start": test_start.isoformat(), "test_end": test_end.isoformat(),
                  "cooldown_end": (test_end + timedelta(days=work["config"]["cooldown_days"])).isoformat()},
        "design": {"type": "national_holdout", "ads_before_test": a.ads_before} if holdout else {"type": "geo_cells"},
        "cells": cells,
        "control": {"geo_ids": sorted(d["control"])},
        "excluded": {"geo_ids": sorted(work["excluded"]), "reasons": dict(work["excluded"])},
        "method": {"estimator": "ridge_ascm", "fixed_effects": True, "lambda_selection": "cv_1se", "inference": "conformal",
                   "permutations": {"kind": "moving_block"}, "placebo_calibration": {"n": 40}, "test_statistic": "abs_sum",
                   "alpha": 0.1, "report_levels": [0.9, 0.95], "head_to_head": "joint_conformal_projection",
                   "donor_min_nonzero_share": 0.5, "seed": work["config"]["seed"]},
        "thresholds": {"pre_fit_nrmse_max": fit_by, "leakage_warn_share": 0.05, "spend_share_tolerance_pp": 5,
                       "min_budget_delivery": 0.9, "power_target": 0.8,
                       **({"pre_fit_period": "week"} if work["result"].get("fit_period") == "week" else {})},
        "decision": {"primary_metric": "cell_lift" if n == 1 else ("delta_icpa" if kpis[0] == "orders" else "delta_iroas"),
                     "meaningful_effect_basis": a.basis},
        "assignment": {"method": "stratified_random_search", "candidates_searched": work["result"]["funnel"]["generated"],
                       "design_rank": a.choose, "label_assignment": "coin_flip" if coin else "user"},
        "vendor_targeting_confirmed": [{"cell_id": c_["id"], "confirmed": True} for c_ in cells],
        "data_fingerprint": work["fingerprint"],
    }
    if a.basis == "target_icpa":
        c["decision"]["target_icpa"] = rnd(a.target, 2)
    if a.basis == "breakeven_iroas":
        c["decision"]["breakeven_iroas"] = rnd(a.target, 4)
    planned = {cells[k]["id"]: rnd(mde[order.index(k)], 4) for k in range(n) if mde[order.index(k)]}
    if planned:
        c["decision"]["planned_mde_lift"] = planned
    if coin:
        c["assignment"]["coin_flip_result"] = {f"market_set_{s + 1}": f"cell_{k + 1}" for s, k in enumerate(coin)}
    if a.advertiser:
        c["advertiser_label"] = a.advertiser.strip()
    if not work["excluded"]:
        del c["excluded"]["reasons"]
    appendix = {"note": "Design diagnostics. Not part of the fingerprint; safe to delete before sharing.",
                "design": {"fit": d["fit"], "pre_fit": d.get("pre_fit"), "shares": d["shares"], "balance": d["balance"],
                           "balance_score": d["balance_score"], "share_in_test": d["share_in_test"],
                           **({"holdout_share": d["control_share"]} if holdout else {})},
                "mde": [{"label": cells[k]["label"], "test_days": days, "mde": mde[order.index(k)],
                         "detectable_icpa": (curves[order.index(k)] or {}).get("money", {}).get("detectable_icpa")} for k in range(n)],
                "search_settings": work["result"].get("settings"), "made_with": f"FOSIT skill CLI, engine {FOSIT_REF}"}
    return c, appendix


def cmd_lock(a) -> None:
    work = json.loads((Path(a.workdir) / "designs.json").read_text())
    designs = work["result"]["designs"]
    if not designs:
        sys.exit("No designs to lock: the search found none that passed every check.")
    if not 1 <= a.choose <= len(designs):
        sys.exit(f"--choose must be between 1 and {len(designs)}.")
    if not a.confirm_targeting:
        sys.exit("Every vendor must confirm it can target exactly its markets (and keep held-out markets dark) before a plan "
                 "is locked. Ask, then pass --confirm-targeting.")
    if work["config"]["design"] == "national_holdout" and a.ads_before not in ("off", "always_on"):
        sys.exit("A holdout plan needs --ads-before off|always_on: was the campaign off everywhere, or on everywhere, during the "
                 "history? If it ran in only some markets, FOSIT can't measure it cleanly.")
    if a.basis in ("target_icpa", "breakeven_iroas") and not a.target:
        sys.exit(f"--basis {a.basis} needs --target.")
    d = designs[a.choose - 1]
    commitment, appendix = build_commitment(work, d, a)
    h = plan_hash(commitment)
    plan = {"fosit_plan_version": "1.0", "commitment": commitment,
            "hash": {"algorithm": "SHA-256", "canonicalization": "RFC8785", "value": h}, "appendix": appendix}
    out = Path(a.out or a.workdir)
    slug = "".join(ch if ch.isalnum() else "-" for ch in a.name.lower()).strip("-")[:40] or "plan"
    plan_path = out / f"{slug}-{h[:8]}.fosit-plan.json"
    write(plan_path, json.dumps(plan, indent=2))
    names = work["names"]
    dd = commitment["dates"]
    holdout = commitment["design"]["type"] == "national_holdout"
    lines = [f"# Locked plan: {a.name}", "", f"**Fingerprint (SHA-256):** `{h}`  ", f"**Short code:** `{h[:8].upper()}`", "",
             f"- Ads {dd['test_start']} to {dd['test_end']} ({a.weeks} weeks); cooldown to {dd['cooldown_end']}",
             f"- History used: {dd['pre_start']} to {dd['pre_end']}", ""]
    if holdout:
        lines.append(f"## Held out (NO ads from {dd['test_start']} to {dd['cooldown_end']}): {len(commitment['control']['geo_ids'])} markets")
        lines.append(", ".join(names.get(g, g) for g in commitment["control"]["geo_ids"]))
    for cell in commitment["cells"]:
        lines += ["", f"## {cell['label']}: {len(cell['geo_ids'])} markets, budget {money(cell['budget'], commitment['currency'])}",
                  ", ".join(names.get(g, g) for g in cell["geo_ids"])]
    if not holdout:
        lines += ["", f"## Control (no test ads from anyone): {len(commitment['control']['geo_ids'])} markets",
                  ", ".join(names.get(g, g) for g in commitment["control"]["geo_ids"])]
    write(out / "plan-summary.md", "\n".join(lines) + "\n")
    who = "the held-out markets get no CTV from anyone" if holdout else "control markets get no test ads"
    email = (f"Subject: Locked test plan: {a.name} (fingerprint {h[:8].upper()})\n\nHi all,\n\nAttached is the locked plan for "
             f"\"{a.name}\" (plan file and summary). Ads run {dd['test_start']} to {dd['test_end']}, each vendor only in the markets "
             f"listed for it; {who} until {dd['cooldown_end']}.\n\nPlan fingerprint (SHA-256):\n{h}\n\nPlease confirm you can target "
             f"exactly your markets. When we read the results, this fingerprint is checked to show the plan wasn't changed.\n"
             + (f"\nAfter the cooldown ends ({dd['cooldown_end']}), read the results here: {a.read_url}\n" if a.read_url else ""))
    write(out / "email.txt", email)
    print("\n".join(lines[:7]))
    if commitment["assignment"]["label_assignment"] == "coin_flip":
        flips = ", ".join(f"{commitment['cells'][int(k.split('_')[1]) - 1]['label']} got market set {s.split('_')[2]}"
                          for s, k in commitment["assignment"]["coin_flip_result"].items())
        print(f"\nCoin flip: {flips}. The market lists in plan-summary.md are the final ones; the cell names in designs.md "
              "are from before the flip.")
    print(f"\nWrote {plan_path}, {out / 'plan-summary.md'} and {out / 'email.txt'}.")
    print("Send the plan file, the summary and the fingerprint to the advertiser and every vendor BEFORE launch: that email is the proof the plan came first.")


def cmd_verify(a) -> None:
    plan = json.loads(Path(a.plan).read_text())
    h = plan_hash(plan["commitment"])
    print(f"Recomputed fingerprint: {h}")
    print("Self-consistent:", "yes" if h == plan["hash"]["value"] else "NO: the plan file was edited after it was locked")
    if a.fingerprint:
        given = a.fingerprint.replace(" ", "").lower()
        ok = h == given if len(given) == 64 else h.startswith(given)
        print("Matches the fingerprint you gave:", "yes" if ok else "NO: this is not the plan that was sent before launch")
        if len(given) < 64 and ok:
            print("(Matched a short code only; paste the full 64-character fingerprint for a check that can't be faked.)")


VERDICT = {"positive": "✓ Positive lift", "no_detectable_lift": "– No detectable lift", "inconclusive": "? Inconclusive",
           "negative": "! Negative lift: investigate"}


def rng(iv, f):
    if not iv:
        return "–"
    lo, hi = iv
    if lo is None and hi is None:
        return "not defined"
    if hi is None:
        return f"at least {f(lo)}, no upper limit"
    if lo is None:
        return f"up to {f(hi)}"
    return f"{f(lo)} to {f(hi)}"


def cmd_read(a) -> None:
    from fosit import api
    plan = json.loads(Path(a.plan).read_text())
    c = plan["commitment"]
    h = plan_hash(c)
    loaded = api.load_history(Path(a.sales).read_text(encoding="utf-8-sig"), c["geo"]["unit"])
    problems = [i for i in loaded["issues"] if i["severity"] == "error"]
    if problems:
        print(issues_md(loaded["issues"]))
        sys.exit("The sales file has errors.")
    spend_info = None
    if a.spend:
        spend_info = api.load_spend(Path(a.spend).read_text(encoding="utf-8-sig"), c)
        if not spend_info["ok"]:
            print(issues_md(spend_info["issues"]))
            sys.exit("The spend & delivery file has errors.")
    today = a.today or date.today().isoformat()
    r = api.run_read(c, h, today, plan.get("appendix"))
    if not r["ok"]:
        sys.exit("Can't read this plan with this data: " + " ".join(r["errors"]))
    out = Path(a.out)
    write(out / "results.json", json.dumps(r, indent=1))
    write(out / "results.csv", r["csv"])

    cur = c["currency"]
    lv = str(r["decision_level"])
    unit_of = lambda kpi: (lambda x: money(x, cur)) if kpi == "revenue" else num
    # honesty checks: plan match and other changes need the person, so they come from flags
    checks = []
    if h != plan["hash"]["value"]:
        checks.append(("FAIL", "Plan match", "The plan file was edited after it was locked. This is NOT THE PRE-REGISTERED ANALYSIS."))
    elif not a.fingerprint:
        checks.append(("WARN", "Plan match", "No fingerprint given. Pass the one from the pre-launch email (--fingerprint) to prove the plan wasn't changed."))
    else:
        g = a.fingerprint.replace(" ", "").lower()
        ok = h == g if len(g) == 64 else h.startswith(g)
        checks.append(("PASS" if ok and len(g) == 64 else "WARN" if ok else "FAIL", "Plan match",
                       "Exactly the plan fingerprinted before launch." if ok and len(g) == 64 else
                       "Matches the short code only." if ok else "Does NOT match the pre-launch fingerprint: NOT THE PRE-REGISTERED ANALYSIS."))
    for ch in r["checks"]:
        checks.append(({"pass": "PASS", "warn": "WARN", "fail": "FAIL"}[ch["status"]], ch["title"], ch["detail"]))
    if a.other_changes is None:
        checks.append(("WARN", "Other changes", "Not confirmed. Ask whether any promotion, price change, stock-out or other channel differed between the test markets and the rest."))
    elif a.other_changes.strip().lower() in ("none", "no"):
        checks.append(("PASS", "Other changes", "Confirmed: nothing else changed differently across markets."))
    else:
        checks.append(("WARN", "Other changes", f"Reported: {a.other_changes}"))

    lines = [f"# Results: {c['test_name']}", ""]
    if r["interim"]:
        lines += [f"**INTERIM:** read before the planned end ({r['window']['planned_end']}). Results can still move.", ""]
    if any(s == "FAIL" and t == "Plan match" for s, t, _ in checks):
        lines += ["**NOT THE PRE-REGISTERED ANALYSIS.**", ""]
    lines += ["## Bottom line", ""]
    for cell in r["cells"]:
        m = cell["kpis"][r["primary_kpi"]]
        f = unit_of(r["primary_kpi"])
        where = f" in its {cell['n_geos']} markets" if r.get("design") == "national_holdout" else ""
        s = (f"**{VERDICT[cell['verdict']]}.** {cell['label']} drove {f(m['incremental'])} incremental {r['primary_kpi']}{where} "
             f"({pct(r['decision_level'], 0)} range: {rng(m['intervals'][lv]['incremental'], f)})")
        if r["primary_kpi"] == "orders" and m.get("spend"):
            ic = m["intervals"][lv].get("icpa")
            if m.get("icpa") and m["intervals"][lv]["incremental"][0] and m["intervals"][lv]["incremental"][0] > 0:
                s += f" at an iCPA of {money(m['icpa'], cur)} (range {rng(ic, lambda x: money(x, cur))})"
            elif ic and ic[0]:
                s += f"; iCPA at least {money(ic[0], cur)} (no upper limit: zero extra orders can't be ruled out)"
        if r["primary_kpi"] == "revenue" and m.get("spend") and m.get("iroas") is not None:
            s += f" for an iROAS of {m['iroas']:.2f} (range {rng(m['intervals'][lv].get('iroas'), lambda x: f'{x:.2f}')})"
        lines.append(s + ".")
        lines.append(f"  _{cell['verdict_reason']}_")
    for hh in r["head_to_head"]:
        if hh["kpi"] != r["primary_kpi"]:
            continue
        name = r["primary_metric"] if r["primary_metric"] in hh["metrics"] and hh["metrics"][r["primary_metric"]]["intervals"].get(lv) else "delta_incremental_per_1000"
        m = hh["metrics"].get(name)
        if m:
            label = {"delta_icpa": "Difference in iCPA", "delta_iroas": "Difference in iROAS",
                     "delta_incremental_per_1000": f"Difference in incremental {hh['kpi']} per 1,000 spent"}.get(name, name)
            est = "–" if m["estimate"] is None else "{:,.2f}".format(m["estimate"])
            lines.append(f"\n**Head-to-head:** {label} ({hh['a_label']} minus {hh['b_label']}): "
                         f"{est} ({pct(r['decision_level'], 0)} range: "
                         f"{rng(m['intervals'].get(lv), lambda x: f'{x:,.2f}')}). "
                         f"{'Distinguishable from zero' if m['distinguishable'] else 'Not distinguishable on this evidence'}.")
            lines.append("_The cells ran in different markets, so this compares vendor + markets; FOSIT balanced the markets at planning time._")
    lines += ["", "## Honesty checks", "", "| | Check | Detail |", "|---|---|---|"]
    lines += [f"| {s} | {t} | {d} |" for s, t, d in checks]
    lines += ["", "## Per cell", ""]
    for cell in r["cells"]:
        lines.append(f"### {cell['label']} ({cell['n_geos']} markets, spend {money(cell['spend'], cur)} of {money(cell['budget'], cur)})")
        lines += ["| Measure | Estimate | 90% range | 95% range |", "|---|---|---|---|"]
        for kpi, m in cell["kpis"].items():
            f = unit_of(kpi)
            lines.append(f"| Incremental {kpi} | {f(m['incremental'])} | {rng(m['intervals']['0.9']['incremental'], f)} | {rng(m['intervals']['0.95']['incremental'], f)} |")
            lines.append(f"| Lift in {kpi} | {pct(m['lift'])} | {rng(m['intervals']['0.9']['lift'], pct)} | {rng(m['intervals']['0.95']['lift'], pct)} |")
            if kpi == "orders" and m.get("spend"):
                mf = lambda x: money(x, cur)
                lines.append(f"| iCPA | {money(m.get('icpa'), cur)} | {rng(m['intervals']['0.9'].get('icpa'), mf)} | {rng(m['intervals']['0.95'].get('icpa'), mf)} |")
            if kpi == "revenue" and m.get("spend"):
                rf = lambda x: f"{x:.2f}"
                lines.append(f"| iROAS | {m['iroas']:.2f} | {rng(m['intervals']['0.9'].get('iroas'), rf)} | {rng(m['intervals']['0.95'].get('iroas'), rf)} |")
            pl = m.get("placebo") or {}
            lines.append(f"| p-value ({kpi}) | {m['p_value']:.3f} | pre-period fit error {pct(m['pre_fit_nrmse'])} | "
                         f"placebo check: {pl.get('n', 0)} fake cells{', range widened' if (pl.get('widened') or {}).get('0.9') else ''} |")
        lines.append("")
    lines += ["## How this was computed", "",
              f"Ridge-augmented synthetic control with conformal inference and placebo calibration, every setting fixed in the plan "
              f"(fingerprint `{h}`), engine fingerprint `{c['tool']['core_sha256'][:16]}…`. Method: "
              f"{FOSIT_REPO}/blob/main/docs/METHODOLOGY.md. Window {r['window']['start']} to {r['window']['end']} ({r['window']['days']} days)."]
    write(out / "report.md", "\n".join(lines) + "\n")
    print("\n".join(lines[: lines.index("## Per cell")]))
    print(f"\nWrote {out / 'report.md'}, {out / 'results.csv'} and {out / 'results.json'}.")


def main() -> None:
    p = argparse.ArgumentParser(description="FOSIT geo-lift tests from the command line.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup", help="install or check the engine")
    s = sub.add_parser("check", help="validate a daily sales-by-market file")
    s.add_argument("sales"); s.add_argument("--unit", choices=["cbsa", "state", "custom"], required=True)
    s = sub.add_parser("orders", help="turn an order export with ZIP codes into daily sales by market")
    s.add_argument("orders"); s.add_argument("--unit", choices=["cbsa", "state", "custom"], required=True)
    s.add_argument("--mapping", help="your own zip,geo_id CSV (required for --unit custom)"); s.add_argument("--out", required=True)
    s = sub.add_parser("sample", help="write clearly-synthetic sample data to try FOSIT")
    s.add_argument("--unit", choices=["cbsa", "state"], default="cbsa"); s.add_argument("--end"); s.add_argument("--seed", type=int, default=2026)
    s.add_argument("--out", required=True)
    s = sub.add_parser("plan", help="search fair designs and simulate their sensitivity")
    s.add_argument("sales"); s.add_argument("--unit", choices=["cbsa", "state", "custom"], required=True)
    s.add_argument("--design", choices=["cells", "holdout", "split"], default="cells")
    s.add_argument("--cells", type=int, help="number of cells (cells: 1-6, default 2; split: vendors 2-4)")
    s.add_argument("--labels", help="comma-separated cell names, e.g. 'Vendor A,Vendor B'")
    s.add_argument("--budget", type=float, required=True, help="total budget during the test")
    s.add_argument("--split", help="budget split per cell in percent, e.g. 50,50")
    s.add_argument("--currency", default="USD"); s.add_argument("--kpi", choices=["orders", "revenue"], default="orders")
    s.add_argument("--test-start", required=True, help="first day of ads, YYYY-MM-DD")
    s.add_argument("--weeks", default="3,4,6,8", help="test lengths to compare, in weeks")
    s.add_argument("--cooldown", type=int, default=7, choices=[0, 7, 14])
    s.add_argument("--pre-weeks", type=int, default=26, help="history to build twins from (up to what the file has)")
    s.add_argument("--exclude", action="append", help="market to leave out, as ID or ID:reason (repeatable)")
    s.add_argument("--share-min", type=float); s.add_argument("--share-max", type=float)
    s.add_argument("--seed", type=int, default=int.from_bytes(os.urandom(3), "big"))
    s.add_argument("--fit-period", choices=["auto", "day", "week"], default="auto",
                   help="judge twin fit day by day or on weekly totals (auto: weekly when sales are small)")
    s.add_argument("--show", type=int, default=5); s.add_argument("--out", required=True)
    s = sub.add_parser("lock", help="lock a design into a pre-registered plan file")
    s.add_argument("workdir"); s.add_argument("--choose", type=int, default=1); s.add_argument("--weeks", type=int, required=True)
    s.add_argument("--name", required=True); s.add_argument("--advertiser")
    s.add_argument("--basis", choices=["planned_mde", "target_icpa", "breakeven_iroas"], default="planned_mde")
    s.add_argument("--target", type=float, help="target iCPA or break-even iROAS, with --basis")
    s.add_argument("--ads-before", choices=["off", "always_on"], help="holdout designs: campaign status during the history")
    s.add_argument("--coin-flip", action="store_true", help="let a fair coin decide which cell gets which market set")
    s.add_argument("--confirm-targeting", action="store_true", help="every vendor confirmed it can target its markets")
    s.add_argument("--read-url", help="link people should use to read results later (goes into the email)")
    s.add_argument("--out")
    s = sub.add_parser("verify", help="recompute a plan's fingerprint")
    s.add_argument("plan"); s.add_argument("--fingerprint")
    s = sub.add_parser("read", help="read the results of a locked plan")
    s.add_argument("plan"); s.add_argument("--sales", required=True); s.add_argument("--spend")
    s.add_argument("--fingerprint", help="the fingerprint from the pre-launch email")
    s.add_argument("--other-changes", help="'none', or what changed differently across markets during the test")
    s.add_argument("--today"); s.add_argument("--out", required=True)
    a = p.parse_args()
    ensure_engine()
    {"setup": cmd_setup, "check": cmd_check, "orders": cmd_orders, "sample": cmd_sample, "plan": cmd_plan,
     "lock": cmd_lock, "verify": cmd_verify, "read": cmd_read}[a.cmd](a)


if __name__ == "__main__":
    main()
