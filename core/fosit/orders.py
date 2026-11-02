"""Order-level export helper: order rows -> KPI history by geo and day, in the browser.

SCHEMA.md §2. ZIPs are mapped with the shipped Census crosswalk (geo_data/zcta_to_geo.csv)
or a user-supplied zip -> geo_id mapping. Unmapped ZIPs are counted and reported,
never silently dropped.
"""

from __future__ import annotations

import io
from importlib import resources

import pandas as pd

from .panel import Issue, read_kpi_csv

UNMAPPED_ERROR_SHARE = 0.10


def shipped_zip_map(unit: str) -> dict[str, str]:
    text = resources.files("fosit").joinpath("geo_data", "zcta_to_geo.csv").read_text(encoding="utf-8")
    df = pd.read_csv(io.StringIO(text), dtype=str)
    column = {"cbsa": "geo_id", "state": "state"}[unit]
    return dict(zip(df["zcta5"], df[column]))


def user_zip_map(text: str) -> tuple[dict[str, str] | None, list[Issue]]:
    df = read_kpi_csv(text)
    issues = []
    for col in ("zip", "geo_id"):
        if col not in df.columns:
            issues.append(Issue("error", f"mapping_missing_{col}", f"The mapping file needs a '{col}' column."))
    if issues:
        return None, issues
    zips = df["zip"].str.strip().str.zfill(5)
    dup = zips.duplicated(keep=False)
    if dup.any():
        return None, [Issue("error", "mapping_duplicate_zip", f"{int(dup.sum())} rows map the same ZIP more than once.",
                            int(dup.sum()), sorted(zips[dup].unique().tolist()))]
    return dict(zip(zips, df["geo_id"].str.strip())), []


def aggregate_orders(text: str, zip_map: dict[str, str]) -> tuple[pd.DataFrame | None, list[Issue]]:
    """Return a long KPI-history table (date, geo_id, orders[, revenue]) and issues."""
    df = read_kpi_csv(text)
    issues: list[Issue] = []
    for col in ("order_date", "shipping_zip"):
        if col not in df.columns:
            issues.append(Issue("error", f"missing_{col}", f"The order export needs an '{col}' column."))
    if issues:
        return None, issues
    n0 = len(df)
    if "order_id" in df.columns:
        dup = df["order_id"].str.strip().ne("") & df["order_id"].duplicated()
        if dup.any():
            issues.append(Issue("warning", "duplicate_order_id", f"Dropped {int(dup.sum())} repeated order_ids.", int(dup.sum())))
            df = df[~dup]
    raw_zip = df["shipping_zip"].str.strip().str.split("-").str[0]
    padded = raw_zip.str.len().between(3, 4) & raw_zip.str.isdigit()
    if padded.any():
        issues.append(Issue("warning", "zip_padded",
                            f"{int(padded.sum())} ZIPs had lost their leading zeros (common in spreadsheets) and were padded.",
                            int(padded.sum())))
    zips = raw_zip.str.zfill(5)
    dates = pd.to_datetime(df["order_date"].str.strip().str[:10], format="%Y-%m-%d", errors="coerce")
    if dates.isna().any():
        n = int(dates.isna().sum())
        return None, issues + [Issue("error", "bad_order_date", f"{n} orders have a date that doesn't start with YYYY-MM-DD.",
                                     n, (df.index[dates.isna()] + 2).tolist())]
    geo = zips.map(zip_map)
    unmapped = geo.isna()
    if unmapped.any():
        share = float(unmapped.mean())
        sev = "error" if share > UNMAPPED_ERROR_SHARE else "warning"
        issues.append(Issue(sev, "unmapped_zip",
                            f"{int(unmapped.sum()):,} orders ({share:.1%}) have ZIPs we couldn't place in a market"
                            + (" - too many to continue; check the ZIP column." if sev == "error" else " and were left out."),
                            int(unmapped.sum()), sorted(zips[unmapped].unique().tolist())))
        if sev == "error":
            return None, issues
    out = pd.DataFrame({"date": dates.dt.strftime("%Y-%m-%d"), "geo_id": geo, "orders": 1})
    if "revenue" in df.columns:
        out["revenue"] = pd.to_numeric(df["revenue"].str.replace(",", "", regex=False), errors="coerce").fillna(0.0)
    out = out[~unmapped.to_numpy()]
    agg = {"orders": "sum"} | ({"revenue": "sum"} if "revenue" in out.columns else {})
    long = out.groupby(["date", "geo_id"], as_index=False).agg(agg).sort_values(["date", "geo_id"])
    issues.append(Issue("warning" if long.empty else "info", "aggregated",
                        f"Turned {n0:,} orders into {len(long):,} market-day rows.", len(long)))
    return long, issues
