"""Compare FOSIT with GeoLift on every validation case (docs/METHODOLOGY.md §12).

    python validation/compare.py validation/cases validation/out/geolift validation/out/report.md

Two comparisons per case:

  matched  (gating) FOSIT with GeoLift's ridge lambda AND GeoLift's two-sided test statistic
           (sum of |daily residuals|, `sum_abs`). Same model, same test: estimates, p-values
           and interval bounds must agree within the tolerances below.
  defaults (informational) each tool with its own defaults: FOSIT selects lambda with 7-day
           block CV and tests the average effect (|sum of residuals|); GeoLift selects lambda
           with 1-day holdouts and tests every day (sum of |residuals|). Shown side by side
           with each tool's distance from the known truth. Never fails the job.

GeoLift searches interval bounds on a fixed grid (mean ATT +/- 6 x RMS, 250 points) and falls
back to jackknife+ when no grid point is accepted. A GeoLift bound at the grid edge, or from the
fallback, isn't a conformal bound and is skipped (reported as such).

Exit code 1 if any gating comparison is outside tolerance.
"""

import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core"))
from fosit import estimate as E  # noqa: E402
from fosit.panel import load_kpi_history  # noqa: E402

TOL = {
    "lift_pp": 0.25,          # absolute, percentage points
    "att_rel": 0.01,          # relative to |GeoLift ATT|, floored at 0.5% of the treated level
    "ci_width_share": 0.05,   # each CI bound, as a share of GeoLift's CI width
    "p_abs": 0.02,            # absolute p-value difference (and same side of alpha)
}
ALPHA = 0.10


def fosit_run(case_dir, case, lam, statistic):
    with open(os.path.join(case_dir, "data.csv")) as f:
        panel, issues = load_kpi_history(f.read())
    if panel is None:
        raise ValueError(f"{case['name']}: {[i.message for i in issues]}")
    treated = case["treated"]
    donors = [g for g in panel.geos if g not in treated]
    n_pre = case["n_pre"]
    series = E.cell_series(panel, case["kpi"], treated, donors, np.arange(n_pre), np.arange(n_pre, panel.n_days),
                           min_nonzero_share=0.0)   # GeoLift does no donor screening
    return E.estimate(series, statistic=statistic, levels=(0.90,), lam=lam, kpi=case["kpi"])


def bound_status(gl, which):
    lo_g, hi_g = gl["ci_grid"]
    step = (hi_g - lo_g) / (gl.get("ci_grid_size", 250) - 1)
    b = gl["att_ci"][which]
    if b is None or not math.isfinite(b):
        return "missing"
    if b < lo_g - 1e-9 * abs(lo_g) or b > hi_g + 1e-9 * abs(hi_g):
        return "jackknife fallback"
    if (which == 0 and b <= lo_g + 0.5 * step) or (which == 1 and b >= hi_g - 0.5 * step):
        return "at GeoLift's grid edge"
    return "ok"


def matched(case, gl, est):
    rows = []
    level = float(np.mean(est.observed[: est.n_pre]))

    def check(name, ours, theirs, diff, tol, skip=""):
        ok = True if skip else (diff <= tol if math.isfinite(diff) else False)
        rows.append({"q": name, "fosit": ours, "geolift": theirs, "diff": diff, "tol": tol, "ok": ok, "skip": skip})

    check("lift (pp)", 100 * est.lift, 100 * gl["lift"], abs(100 * (est.lift - gl["lift"])), TOL["lift_pp"])
    denom = max(abs(gl["att"]), 0.005 * level)
    check("ATT (relative)", est.att, gl["att"], abs(est.att - gl["att"]) / denom, TOL["att_rel"])
    same_side = (est.p_value <= ALPHA) == (gl["p_value"] <= ALPHA)
    check("p-value", est.p_value, gl["p_value"], abs(est.p_value - gl["p_value"]) if same_side else math.inf, TOL["p_abs"])
    lo, hi = est.intervals[0.90]
    glo, ghi = gl["att_ci"]
    width = abs(ghi - glo) if all(math.isfinite(x) for x in (glo, ghi)) else float("nan")
    for i, (ours, theirs, name) in enumerate(((lo, glo, "CI low"), (hi, ghi, "CI high"))):
        status = bound_status(gl, i)
        skip = "" if status == "ok" else status
        diff = abs(ours - theirs) / width if math.isfinite(ours) and width and math.isfinite(width) else math.inf
        check(f"{name} (share of width)", ours, theirs, diff, TOL["ci_width_share"], skip)
    return rows


def fmt(x, digits=4):
    return "–" if x is None or (isinstance(x, float) and not math.isfinite(x)) else f"{x:.{digits}g}"


def main(cases_dir, geolift_dir, report_path):
    lines = ["# FOSIT vs GeoLift validation report", "",
             "See the docstring of `validation/compare.py` and docs/METHODOLOGY.md §12 for what is compared and why.", ""]
    failures = 0
    for name in sorted(os.listdir(cases_dir)):
        case_dir = os.path.join(cases_dir, name)
        if not os.path.isdir(case_dir):
            continue
        result_path = os.path.join(geolift_dir, f"{name}.json")
        if not os.path.exists(result_path):
            lines += [f"## {name}", "", "**MISSING GeoLift output**", ""]
            failures += 1
            continue
        case = json.load(open(os.path.join(case_dir, "case.json")))
        gl = json.load(open(result_path))
        lines += [f"## {name}", "", f"GeoLift {gl.get('geolift_version')} / augsynth {gl.get('augsynth_version')}, "
                  f"conformal_type={gl.get('conformal_type')}, GeoLift lambda={fmt(gl.get('lambda'))}, "
                  f"true incremental={case['true_incremental']:.1f}", ""]

        lam = gl.get("lambda")
        if lam is None or (isinstance(lam, float) and math.isnan(lam)):
            lines += ["*matched: GeoLift returned no lambda; skipped*", ""]
        else:
            est = fosit_run(case_dir, case, float(lam), "sum_abs")
            if gl.get("y_hat"):
                gap = np.max(np.abs(np.array(gl["y_hat"]) - est.counterfactual)) / max(np.mean(est.observed), 1e-9)
                lines.append(f"*matched: max counterfactual gap = {gap:.4%} of the treated level*")
                lines.append("")
            lines += ["**matched (gating)**: GeoLift's lambda and test statistic", "",
                      "| quantity | FOSIT | GeoLift | diff | tolerance | |", "|---|---|---|---|---|---|"]
            for r in matched(case, gl, est):
                failures += not r["ok"]
                mark = f"skipped: {r['skip']}" if r["skip"] else ("✅" if r["ok"] else "❌")
                lines.append(f"| {r['q']} | {fmt(r['fosit'])} | {fmt(r['geolift'])} | {fmt(r['diff'])} | {r['tol']} | {mark} |")
            lines.append("")

        # informational: each tool's defaults, scored against the truth
        d = fosit_run(case_dir, case, None, "abs_sum")
        truth_att = case["true_incremental"] / (len(case["treated"]) * case["n_post"])
        g_lo, g_hi = gl["att_ci"]
        f_lo, f_hi = d.intervals[0.90]
        lines += ["**defaults (informational)**", "",
                  "| tool | lambda | ATT | error vs truth | 90% CI on ATT | covers truth | p-value |", "|---|---|---|---|---|---|---|",
                  f"| FOSIT (abs_sum, 7-day CV) | {fmt(d.lam)} | {fmt(d.att)} | {fmt(d.att - truth_att)} | {fmt(f_lo)} to {fmt(f_hi)} | "
                  f"{'yes' if f_lo <= truth_att <= f_hi else 'no'} | {fmt(d.p_value)} |",
                  f"| GeoLift (sum_abs, 1-day CV) | {fmt(gl.get('lambda'))} | {fmt(gl['att'])} | {fmt(gl['att'] - truth_att)} | "
                  f"{fmt(g_lo)} to {fmt(g_hi)} | {'yes' if g_lo is not None and g_lo <= truth_att <= g_hi else 'no'} | {fmt(gl['p_value'])} |",
                  ""]
    lines.append(f"**{'PASS' if failures == 0 else f'FAIL ({failures} gating comparisons outside tolerance)'}**")
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
