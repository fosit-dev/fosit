"""Spend and delivery file: validation and per-cell totals (SCHEMA.md §3).

One file holds every cell's rows. Rows are matched to plan cells by label or id.
Spend and impressions outside the measurement window are excluded and reported.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .panel import Issue, read_kpi_csv

UNKNOWN_GEO = "*"


@dataclass
class SpendData:
    rows: pd.DataFrame     # date (Timestamp), cell_id, geo_id, impressions, spend

    def spend_by_cell(self) -> dict[str, float]:
        return self.rows.groupby("cell_id")["spend"].sum().to_dict()


def load_spend(text: str, cells: list[dict], window_start: str, window_end: str) -> tuple[SpendData | None, list[Issue]]:
    """Validate a spend & delivery CSV against the plan's cells and measurement window."""
    df = read_kpi_csv(text)
    issues: list[Issue] = []
    required = ("date", "cell", "geo_id", "impressions", "spend")
    missing = [c for c in required if c not in df.columns]
    if missing:
        return None, [Issue("error", "spend_missing_columns", f"The spend file needs these columns: {', '.join(missing)}.")]
    rownum = df.index + 2
    lookup = {}
    for c in cells:
        lookup[c["id"].strip().lower()] = c["id"]
        lookup[c["label"].strip().lower()] = c["id"]
    cell_id = df["cell"].str.strip().str.lower().map(lookup)
    if cell_id.isna().any():
        bad = sorted(df.loc[cell_id.isna(), "cell"].unique().tolist())
        issues.append(Issue("error", "spend_unknown_cell",
                            f"{int(cell_id.isna().sum())} rows name a cell that isn't in the plan: {', '.join(bad[:5])}. "
                            f"Use one of: {', '.join(c['label'] for c in cells)}.", int(cell_id.isna().sum()), bad))
    dates = pd.to_datetime(df["date"].str.strip(), format="%Y-%m-%d", errors="coerce")
    if dates.isna().any():
        issues.append(Issue("error", "spend_bad_date", f"{int(dates.isna().sum())} rows have a date that isn't YYYY-MM-DD.",
                            int(dates.isna().sum()), rownum[dates.isna()].tolist()))
    nums = {}
    for col in ("impressions", "spend"):
        v = pd.to_numeric(df[col].str.strip().str.replace(",", "", regex=False), errors="coerce")
        bad = v.isna() | (v < 0)
        if bad.any():
            issues.append(Issue("error", f"spend_bad_{col}", f"{int(bad.sum())} rows have a missing or negative {col}.",
                                int(bad.sum()), rownum[bad].tolist()))
        nums[col] = v
    if any(i.severity == "error" for i in issues):
        return None, issues

    out = pd.DataFrame({"date": dates, "cell_id": cell_id, "geo_id": df["geo_id"].str.strip(),
                        "impressions": nums["impressions"], "spend": nums["spend"]})
    dup = out.duplicated(["date", "cell_id", "geo_id"], keep=False)
    if dup.any():
        return None, issues + [Issue("error", "spend_duplicates", f"{int(dup.sum())} rows repeat the same date, cell and geo_id.",
                                     int(dup.sum()), rownum[dup].tolist())]
    inside = out["date"].between(pd.Timestamp(window_start), pd.Timestamp(window_end))
    if (~inside).any():
        dropped = out[~inside]
        issues.append(Issue("warning", "spend_outside_window",
                            f"{len(dropped)} rows ({dropped['spend'].sum():,.0f} spend) are dated outside the test and cooldown "
                            f"({window_start} to {window_end}) and were left out.", len(dropped)))
        out = out[inside]
    for c in cells:
        if not (out["cell_id"] == c["id"]).any():
            issues.append(Issue("warning", "spend_cell_missing", f"No spend rows for {c['label']}: its iCPA and iROAS can't be computed."))
    return SpendData(out.reset_index(drop=True)), issues


def leakage(spend: SpendData, cell_id: str, plan_geos: dict[str, set], control: set, excluded: set) -> dict:
    """Where a cell's impressions went (METHODOLOGY.md §11): own markets, control, other cells, outside the study, unknown."""
    rows = spend.rows[spend.rows["cell_id"] == cell_id]
    total = float(rows["impressions"].sum())
    own = plan_geos[cell_id]
    others = set().union(*(g for k, g in plan_geos.items() if k != cell_id)) if len(plan_geos) > 1 else set()
    by = {"own": 0.0, "control": 0.0, "other_cells": 0.0, "outside_study": 0.0, "unknown": 0.0}
    for geo, imp in rows.groupby("geo_id")["impressions"].sum().items():
        key = ("unknown" if geo == UNKNOWN_GEO else "own" if geo in own else "control" if geo in control
               else "other_cells" if geo in others else "outside_study")
        by[key] += float(imp)
    share = {k: (v / total if total > 0 else 0.0) for k, v in by.items()}
    leak = share["control"] + share["other_cells"] + share["outside_study"]
    return {"impressions": total, "by_destination": by, "share": share, "leak_share": leak,
            "unverifiable_share": share["unknown"], "excluded_geos_hit": sorted(set(rows["geo_id"]) & excluded)}
