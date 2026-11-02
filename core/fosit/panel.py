"""Data preparation: KPI history validation and the geo x day panel.

METHODOLOGY.md §3 (data preparation) and SCHEMA.md §1 (KPI history rules).

The panel is the only data structure the statistics see: one matrix per KPI,
rows = geos, columns = consecutive days. Every fix we make to the user's data
(zero-filling, dropped rows) is recorded as an Issue so the UI can show it.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

KPIS = ("orders", "revenue")
GEO_ID_PATTERN = r"^[A-Za-z0-9_.:-]{1,64}$"
MIN_PRE_WEEKS_WARN = 8
MAX_LISTED = 20  # how many example rows an Issue carries


@dataclass
class Issue:
    """One validation finding. severity: 'error' stops the run, 'warning' is shown and reported."""

    severity: str
    code: str
    message: str
    count: int = 0
    examples: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"severity": self.severity, "code": self.code, "message": self.message,
                "count": int(self.count), "examples": self.examples[:MAX_LISTED]}


@dataclass
class Panel:
    """Geo x day KPI matrices over a contiguous daily date range."""

    dates: pd.DatetimeIndex
    geos: list[str]
    kpis: dict[str, np.ndarray]  # kpi name -> (n_geos, n_days) float array

    def __post_init__(self) -> None:
        self._index = {g: i for i, g in enumerate(self.geos)}

    @property
    def n_days(self) -> int:
        return len(self.dates)

    def rows(self, geo_ids) -> np.ndarray:
        """Row indices for geo ids (KeyError on unknown ids)."""
        return np.array([self._index[g] for g in geo_ids], dtype=int)

    def day(self, date) -> int:
        """Column index of a calendar date (KeyError if outside the panel)."""
        return int(self.dates.get_loc(pd.Timestamp(date)))

    def window(self, start, end) -> "Panel":
        """Sub-panel for [start, end] inclusive."""
        i, j = self.day(start), self.day(end) + 1
        return Panel(self.dates[i:j], list(self.geos), {k: v[:, i:j] for k, v in self.kpis.items()})

    def summary(self) -> dict:
        return {
            "first_date": self.dates[0].strftime("%Y-%m-%d"),
            "last_date": self.dates[-1].strftime("%Y-%m-%d"),
            "days": self.n_days,
            "weeks": round(self.n_days / 7, 1),
            "geos": len(self.geos),
            "kpis": sorted(self.kpis),
            "totals": {k: float(v.sum()) for k, v in self.kpis.items()},
        }


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(c).lstrip(chr(0xFEFF)).strip().lower() for c in df.columns]
    return df


def read_kpi_csv(text: str) -> pd.DataFrame:
    """Parse CSV text with every column as string, so validation sees the raw values."""
    df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False, skipinitialspace=True)
    return _normalise_columns(df)


def _numeric(df: pd.DataFrame, col: str, issues: list[Issue]) -> pd.Series:
    raw = df[col].str.strip()
    values = pd.to_numeric(raw.str.replace(",", "", regex=False), errors="coerce")
    bad = values.isna() & (raw != "")
    if bad.any():
        issues.append(Issue("error", f"{col}_not_numeric",
                            f"{int(bad.sum())} rows have a non-numeric {col}. Fix or blank those cells.",
                            int(bad.sum()), (df.index[bad] + 2).tolist()))
    return values


def build_panel(df: pd.DataFrame, valid_geos: set[str] | None = None) -> tuple[Panel | None, list[Issue]]:
    """Validate a KPI-history table (SCHEMA.md §1) and pivot it to a Panel.

    `df` columns must already be normalised (lower-case). Row numbers in Issue
    examples are spreadsheet rows (header = row 1).
    Returns (None, issues) when any error is found.
    """
    issues: list[Issue] = []
    extra = [c for c in df.columns if c not in ("date", "geo_id") + KPIS]
    if extra:
        issues.append(Issue("warning", "extra_columns", f"Ignored columns: {', '.join(extra)}.", len(extra), extra))
    for col in ("date", "geo_id"):
        if col not in df.columns:
            issues.append(Issue("error", f"missing_{col}", f"The file needs a '{col}' column."))
    kpis = [k for k in KPIS if k in df.columns]
    if not kpis:
        issues.append(Issue("error", "missing_kpi", "The file needs an 'orders' column, a 'revenue' column, or both."))
    if any(i.severity == "error" for i in issues):
        return None, issues

    df = df.copy()
    rownum = df.index + 2
    df["geo_id"] = df["geo_id"].str.strip()
    dates = pd.to_datetime(df["date"].str.strip(), format="%Y-%m-%d", errors="coerce")
    bad_date = dates.isna()
    if bad_date.any():
        issues.append(Issue("error", "bad_date", f"{int(bad_date.sum())} rows have a date that isn't YYYY-MM-DD.",
                            int(bad_date.sum()), rownum[bad_date].tolist()))
    bad_geo = ~df["geo_id"].str.match(GEO_ID_PATTERN)
    if bad_geo.any():
        issues.append(Issue("error", "bad_geo_id", f"{int(bad_geo.sum())} rows have an empty or invalid geo_id.",
                            int(bad_geo.sum()), rownum[bad_geo].tolist()))
    values = {k: _numeric(df, k, issues) for k in kpis}
    if any(i.severity == "error" for i in issues):
        return None, issues

    df["date"] = dates
    for k in kpis:
        df[k] = values[k]
    if "orders" in kpis:
        if (df["orders"] < 0).any():
            n = int((df["orders"] < 0).sum())
            issues.append(Issue("error", "negative_orders", f"{n} rows have negative orders.", n,
                                rownum[df["orders"] < 0].tolist()))
        frac = df["orders"].notna() & (df["orders"] % 1 != 0)
        if frac.any():
            issues.append(Issue("warning", "fractional_orders",
                                f"{int(frac.sum())} rows have fractional orders (fine for modelled conversions).", int(frac.sum())))
    if "revenue" in kpis and (df["revenue"] < 0).any():
        n = int((df["revenue"] < 0).sum())
        issues.append(Issue("warning", "negative_revenue", f"{n} rows have negative revenue (e.g. returns).", n,
                            rownum[df["revenue"] < 0].tolist()))
    dup = df.duplicated(["date", "geo_id"], keep=False)
    if dup.any():
        issues.append(Issue("error", "duplicate_rows",
                            f"{int(dup.sum())} rows repeat the same date and geo_id. Each pair must appear once.",
                            int(dup.sum()), rownum[dup].tolist()))
    if any(i.severity == "error" for i in issues):
        return None, issues

    if valid_geos is not None:
        unknown = ~df["geo_id"].isin(valid_geos)
        if unknown.any():
            ids = sorted(df.loc[unknown, "geo_id"].unique())
            issues.append(Issue("warning", "unknown_geo",
                                f"{len(ids)} geo_ids aren't in the chosen geo unit; their {int(unknown.sum())} rows were excluded.",
                                int(unknown.sum()), ids))
            df = df[~unknown]

    all_days = pd.date_range(df["date"].min(), df["date"].max(), freq="D")
    present = pd.DatetimeIndex(df["date"].unique())
    gap = all_days.difference(present)
    if len(gap):
        issues.append(Issue("error", "date_gap",
                            f"{len(gap)} days have no rows at all. That's a gap in the export, not zero sales.",
                            len(gap), [d.strftime("%Y-%m-%d") for d in gap]))
        return None, issues

    geos = sorted(df["geo_id"].unique())
    expected = len(geos) * len(all_days)
    filled = expected - len(df)
    if filled:
        issues.append(Issue("warning", "zero_filled",
                            f"We filled {filled:,} missing market-days with 0 (normal when exports skip days with no sales).",
                            filled))
    if len(all_days) < MIN_PRE_WEEKS_WARN * 7:
        issues.append(Issue("warning", "short_history",
                            f"Only {len(all_days)} days of history. Under {MIN_PRE_WEEKS_WARN} weeks makes the twin and the "
                            "power estimates unreliable; 12+ weeks is recommended.", len(all_days)))

    mats = {}
    for k in kpis:
        wide = df.pivot(index="geo_id", columns="date", values=k).reindex(index=geos, columns=all_days)
        mats[k] = wide.to_numpy(dtype=float, na_value=0.0)
    return Panel(all_days, geos, mats), issues


def load_kpi_history(text: str, valid_geos: set[str] | None = None) -> tuple[Panel | None, list[Issue]]:
    """CSV text -> (Panel, issues). Convenience wrapper used by the web worker and tests."""
    return build_panel(read_kpi_csv(text), valid_geos)


def panel_from_long(df: pd.DataFrame) -> Panel:
    """Build a panel from an already-clean long DataFrame (date as datetime). Raises on errors."""
    panel, issues = build_panel(_normalise_columns(df.astype({c: str for c in df.columns})))
    if panel is None:
        raise ValueError("; ".join(i.message for i in issues if i.severity == "error"))
    return panel
