"""Compare FOSIT with GeoLift on every validation case (docs/METHODOLOGY.md §12).

    python validation/compare.py validation/cases validation/out/geolift validation/out/report.md

Two modes per case:
  pinned  FOSIT uses GeoLift's selected ridge lambda -> isolates estimator + inference
  auto    FOSIT selects its own lambda             -> end-to-end defaults
Exit code 1 if any comparison is outside tolerance.

Tolerances are provisional until the first harness runs (CHANGELOG.md records changes).
"""

import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core"))
from fosit import estimate as E  # noqa: E402
from fosit.panel import load_kpi_history  # noqa: E402

TOLERANCES = {
    # quantity: (pinned, auto)
    "lift_pp": (0.25, 1.0),          # absolute, percentage points
    "att_rel": (0.01, 0.05),         # relative to |GeoLift ATT|, floored at 0.5% of the treated level
    "ci_width_share": (0.05, 0.15),  # each CI bound, as a share of GeoLift's CI width
    "p_abs": (0.02, 0.05),           # absolute p-value difference
}
ALPHA = 0.10


def fosit_run(case_dir: str, case: dict, lam):
    with open(os.path.join(case_dir, "data.csv")) as f:
        panel, issues = load_kpi_history(f.read())
    if panel is None:
        raise ValueError(f"{case['name']}: {[i.message for i in issues]}")
    treated = case["treated"]
    donors = [g for g in panel.geos if g not in treated]
    n_pre = case["n_pre"]
    series = E.cell_series(panel, case["kpi"], treated, donors, np.arange(n_pre), np.arange(n_pre, panel.n_days),
                           min_nonzero_share=0.0)   # GeoLift does no donor screening
    return E.estimate(series, levels=(0.90,), lam=lam, kpi=case["kpi"])


def compare(case: dict, gl: dict, est, mode: int) -> list[dict]:
    rows = []
    level = float(np.mean(est.observed[: est.n_pre]))

    def check(name, ours, theirs, diff, tol):
        ok = diff <= tol if math.isfinite(diff) else False
        rows.append({"quantity": name, "fosit": ours, "geolift": theirs, "diff": diff, "tolerance": tol, "ok": ok})

    check("lift (pp)", 100 * est.lift, 100 * gl["lift"], abs(100 * (est.lift - gl["lift"])), TOLERANCES["lift_pp"][mode])
    denom = max(abs(gl["att"]), 0.005 * level)
    check("ATT (relative)", est.att, gl["att"], abs(est.att - gl["att"]) / denom, TOLERANCES["att_rel"][mode])
    lo, hi = est.intervals[0.90]
    glo, ghi = gl["att_ci"]
    width = abs(ghi - glo) or 1e-12
    check("CI low (share of width)", lo, glo, abs(lo - glo) / width, TOLERANCES["ci_width_share"][mode])
    check("CI high (share of width)", hi, ghi, abs(hi - ghi) / width, TOLERANCES["ci_width_share"][mode])
    same_side = (est.p_value <= ALPHA) == (gl["p_value"] <= ALPHA)
    check("p-value", est.p_value, gl["p_value"], abs(est.p_value - gl["p_value"]) if same_side else math.inf,
          TOLERANCES["p_abs"][mode])
    return rows


def main(cases_dir: str, geolift_dir: str, report_path: str) -> int:
    lines = ["# FOSIT vs GeoLift validation report", "",
             "Tolerances: docs/METHODOLOGY.md §12. Mode 'pinned' uses GeoLift's lambda; 'auto' uses FOSIT's own.", ""]
    failures = 0
    for name in sorted(os.listdir(cases_dir)):
        case_dir = os.path.join(cases_dir, name)
        result_path = os.path.join(geolift_dir, f"{name}.json")
        if not os.path.isdir(case_dir):
            continue
        if not os.path.exists(result_path):
            lines += [f"## {name}", "", "**MISSING GeoLift output**", ""]
            failures += 1
            continue
        with open(os.path.join(case_dir, "case.json")) as f:
            case = json.load(f)
        with open(result_path) as f:
            gl = json.load(f)
        lines += [f"## {name}", "", f"GeoLift {gl.get('geolift_version')} / augsynth {gl.get('augsynth_version')}, "
                  f"conformal_type={gl.get('conformal_type')}, lambda={gl.get('lambda')}, "
                  f"true incremental={case['true_incremental']:.1f}", ""]
        modes = [("pinned", 0, gl.get("lambda")), ("auto", 1, None)]
        for label, mode, lam in modes:
            if label == "pinned" and (lam is None or (isinstance(lam, float) and math.isnan(lam))):
                lines += ["*pinned: GeoLift returned no lambda; skipped*", ""]
                continue
            est = fosit_run(case_dir, case, lam)
            rows = compare(case, gl, est, mode)
            if label == "pinned" and gl.get("y_hat"):
                gap = np.max(np.abs(np.array(gl["y_hat"]) - est.counterfactual)) / max(np.mean(est.observed), 1e-9)
                lines.append(f"*{label}: max counterfactual gap = {gap:.4%} of the treated level*")
                lines.append("")
            lines += [f"**{label}**", "", "| quantity | FOSIT | GeoLift | diff | tolerance | |", "|---|---|---|---|---|---|"]
            for r in rows:
                failures += not r["ok"]
                lines.append(f"| {r['quantity']} | {r['fosit']:.4g} | {r['geolift']:.4g} | {r['diff']:.4g} | "
                             f"{r['tolerance']} | {'✅' if r['ok'] else '❌'} |")
            lines.append("")
    lines.append(f"**{'PASS' if failures == 0 else f'FAIL ({failures} comparisons outside tolerance)'}**")
    os.makedirs(os.path.dirname(report_path) or ".", exist_ok=True)
    with open(report_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 1 if failures else 0


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    a = sys.argv[1:] + [None] * 3
    sys.exit(main(a[0] or os.path.join(here, "cases"), a[1] or os.path.join(here, "out", "geolift"),
                  a[2] or os.path.join(here, "out", "report.md")))
