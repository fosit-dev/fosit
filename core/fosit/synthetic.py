"""Synthetic geo panels with known effects, for tests, examples and validation.

Not part of the statistical method. The generator is a latent factor model,
the setting synthetic control is designed for:

    log mu_it = log size_i + log dow_i(day of week of t) + loading_i . f_t + trend_i * t
    orders_it ~ Gamma-Poisson(mu_it * (1 + lift_it), dispersion)
    revenue_it = orders_it * aov_i * exp(noise)

The truth (injected lift per geo and day, and the realised incremental orders
and revenue) is returned alongside the data so tests can check recovery.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

DOW = np.array([0.92, 0.95, 1.0, 1.0, 1.04, 1.12, 0.97])  # Monday..Sunday


@dataclass
class SyntheticTruth:
    lift: np.ndarray             # (G, T) multiplicative lift applied
    incremental_orders: dict     # cell name -> realised incremental orders (expected value)
    incremental_revenue: dict


def make_panel(n_geos: int = 120, n_days: int = 168, start: str = "2026-01-05", seed: int = 0,
               n_factors: int = 3, factor_sd: float = 0.03, dispersion: float = 30.0,
               median_daily_orders: float = 25.0, size_sigma: float = 1.2,
               lifts: dict | None = None, geo_prefix: str = "G", geo_ids: list | None = None,
               sizes: np.ndarray | None = None, trend_sd: float = 0.0008) -> tuple[pd.DataFrame, SyntheticTruth]:
    """Generate a long-format KPI history (date, geo_id, orders, revenue).

    lifts: {cell_name: (geo_ids, first_day_index, last_day_index, lift)} injects a
    multiplicative lift into those geos on those days (inclusive).
    geo_ids / sizes (expected daily orders per geo) override the generated ones.
    """
    rng = np.random.default_rng(seed)
    geos = list(geo_ids) if geo_ids is not None else [f"{geo_prefix}{i:04d}" for i in range(n_geos)]
    n_geos = len(geos)
    size = median_daily_orders * np.exp(rng.normal(0, size_sigma, n_geos))
    if sizes is not None:
        size = np.asarray(sizes, dtype=float)
    dow_dev = np.exp(rng.normal(0, 0.03, (n_geos, 7)))
    loadings = rng.normal(1.0, 0.5, (n_geos, n_factors))
    trend = rng.normal(0, trend_sd, n_geos)
    f = np.zeros((n_factors, n_days))
    for t in range(1, n_days):
        f[:, t] = 0.95 * f[:, t - 1] + rng.normal(0, factor_sd, n_factors)
    dates = pd.date_range(start, periods=n_days, freq="D")
    dow = (DOW[dates.day_of_week.to_numpy()][None, :] * dow_dev[:, dates.day_of_week.to_numpy()])
    mu = size[:, None] * dow * np.exp(loadings @ f + trend[:, None] * np.arange(n_days))

    lift = np.zeros((n_geos, n_days))
    index = {g: i for i, g in enumerate(geos)}
    for geo_ids, d0, d1, value in (lifts or {}).values():
        lift[np.ix_([index[g] for g in geo_ids], np.arange(d0, d1 + 1))] = value
    mean = mu * (1 + lift)
    orders = rng.poisson(rng.gamma(dispersion, mean / dispersion))
    aov = 80 * np.exp(rng.normal(0, 0.15, n_geos))
    revenue = orders * aov[:, None] * np.exp(rng.normal(0, 0.08, (n_geos, n_days)))

    inc_o, inc_r = {}, {}
    for name, (geo_ids, d0, d1, value) in (lifts or {}).items():
        rows = [index[g] for g in geo_ids]
        extra = mu[np.ix_(rows, np.arange(d0, d1 + 1))] * value
        inc_o[name] = float(extra.sum())
        inc_r[name] = float((extra * aov[rows, None]).sum())

    df = pd.DataFrame({
        "date": np.repeat(dates.strftime("%Y-%m-%d").to_numpy()[None, :], n_geos, 0).ravel(),
        "geo_id": np.repeat(geos, n_days),
        "orders": orders.ravel().astype(int),
        "revenue": np.round(revenue.ravel(), 2),
    })
    return df, SyntheticTruth(lift, inc_o, inc_r)


def population_for(df: pd.DataFrame, seed: int = 0, per_daily_order: float = 900.0) -> dict:
    """Plausible populations roughly proportional to sales, for balance tests."""
    rng = np.random.default_rng(seed + 1)
    mean = df.groupby("geo_id")["orders"].mean()
    return {g: int(m * per_daily_order * np.exp(rng.normal(0, 0.25)) + 5000) for g, m in mean.items()}


def sample_state_history(attributes: list[dict], end: str, n_days: int = 182, seed: int = 2026,
                         orders_per_100k: float = 2.0) -> pd.DataFrame:
    """Synthetic daily sales for the 50 states + DC, roughly proportional to population, ending on `end`.

    Used by the national-holdout example and tests (METHODOLOGY.md §13.6). Clearly synthetic.
    """
    rng = np.random.default_rng(seed)
    ids = [a["geo_id"] for a in attributes]
    pop = np.array([a["population"] for a in attributes], dtype=float)
    sizes = pop / 1e5 * orders_per_100k * np.exp(rng.normal(0, 0.25, len(ids)))
    start = (pd.Timestamp(end) - pd.Timedelta(days=n_days - 1)).strftime("%Y-%m-%d")
    df, _ = make_panel(n_days=n_days, start=start, seed=seed + 100, geo_ids=ids, sizes=sizes)
    return df


def sample_cbsa_history(attributes: list[dict], end: str, n_days: int = 182, seed: int = 2026,
                        n_markets: int = 250, orders_per_100k: float = 1.0) -> pd.DataFrame:
    """Sample data for the app's "Try it with sample data": the largest CBSAs, sales roughly
    proportional to population (with market-to-market variation), ending on `end`.

    Clearly synthetic; never presented as a real advertiser's data.
    """
    rng = np.random.default_rng(seed)
    cbsas = sorted((a for a in attributes if a.get("kind") in ("metro", "micro") and a.get("population")),
                   key=lambda a: -a["population"])[:n_markets]
    ids = [a["geo_id"] for a in cbsas]
    pop = np.array([a["population"] for a in cbsas], dtype=float)
    sizes = pop / 1e5 * orders_per_100k * np.exp(rng.normal(0, 0.35, len(ids)))
    start = (pd.Timestamp(end) - pd.Timedelta(days=n_days - 1)).strftime("%Y-%m-%d")
    df, _ = make_panel(n_days=n_days, start=start, seed=seed, geo_ids=ids, sizes=sizes)
    return df
