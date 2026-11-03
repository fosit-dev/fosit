"""Market selection: fair, well-fitting treatment market sets, one per cell.

METHODOLOGY.md §9. Candidates come from a seeded, stratified random search:
similar-sized geos are grouped into strata of K+1, and within each chosen
stratum one geo is randomly assigned to each cell (the rest stay in control).
In a national holdout (§13) the same search picks the holdout markets instead,
and the cell is every other market.
Candidates are then filtered by share bounds and balance (cheap), screened by
plain synthetic-control holdout fit (fast), and the best are re-scored with the
full ASCM holdout fit. Power (power.py) ranks the final shortlist.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import ascm
from .estimate import DONOR_MIN_NONZERO_SHARE
from .holdout import index_rows
from .panel import Panel

TREND_DAYS = 28


@dataclass
class SelectionConfig:
    n_cells: int = 2
    kpi: str = "orders"
    pre_days: int = 84                  # length of the pre-period the real test will use
    test_days: int = 28                 # holdout length for the fit score
    share_min: float = 0.03
    share_max: float = 0.15
    min_control_share: float = 0.50
    balance_max: float = 0.10
    fit_max: float = 0.10
    n_candidates: int = 2000
    screen_top: int = 60                # candidates re-scored with full ASCM
    shortlist: int = 20
    seed: int = 0
    excluded: set = field(default_factory=set)
    not_eligible: set = field(default_factory=set)   # e.g. {ST}-NONCBSA units
    population: dict | None = None
    donor_min_nonzero_share: float = DONOR_MIN_NONZERO_SHARE
    # National holdout (§13): share_min/share_max bound the holdout's share. With n_cells = 1 the one cell is
    # every market that isn't held out or excluded; with more, those markets are split between the cells (§13.7).
    holdout: bool = False
    min_holdout_geos: int = 10          # a twin built from a handful of markets leans on one or two of them (§13.2)


@dataclass
class Design:
    cells: list[list[str]]              # geo ids per cell, sorted
    control: list[str]
    shares: list[float]                 # share of national KPI per cell (pre-period)
    control_share: float
    balance: dict                       # feature -> relative gap across cells
    balance_score: float
    fit_screen: list[float] = field(default_factory=list)   # SCM holdout nRMSE per cell
    fit: list[float] = field(default_factory=list)          # ASCM holdout nRMSE per cell
    pre_fit: list[float] = field(default_factory=list)      # in-sample nRMSE over the whole pre-period: what Read checks (§9.3)
    target_share: float = 0.0
    power: dict | None = None           # filled by power.py

    @property
    def key(self) -> tuple:
        return tuple(tuple(c) for c in self.cells)

    def to_dict(self) -> dict:
        return {
            "cells": self.cells, "control": self.control, "shares": self.shares,
            "control_share": self.control_share, "balance": self.balance, "balance_score": self.balance_score,
            "fit_screen": self.fit_screen, "fit": self.fit, "pre_fit": self.pre_fit, "power": self.power,
            "share_in_test": float(sum(self.shares)),
        }


def relative_gap(values) -> float:
    """Largest pairwise |a - b| / mean(|a|, |b|) (§9.3)."""
    v = np.asarray(values, dtype=float)
    worst = 0.0
    for i in range(len(v)):
        for j in range(i + 1, len(v)):
            m = (abs(v[i]) + abs(v[j])) / 2
            if m > 0:
                worst = max(worst, abs(v[i] - v[j]) / m)
    return float(worst)


class MarketSelector:
    """Holds the pre-computed per-geo quantities for one planning run."""

    def __init__(self, panel: Panel, cfg: SelectionConfig):
        self.cfg = cfg
        self.panel = panel
        if cfg.kpi not in panel.kpis:
            raise ValueError(f"KPI {cfg.kpi!r} not in data")
        n = min(cfg.pre_days, panel.n_days)
        if n < cfg.test_days + 28:
            raise ValueError("History too short to score fit: need at least test length + 4 weeks.")
        self.cols = np.arange(panel.n_days - n, panel.n_days)
        Y = panel.kpis[cfg.kpi][:, self.cols]
        self.Y = Y
        self.geos = np.array(panel.geos)
        usable = np.array([g not in cfg.excluded for g in panel.geos])
        nonzero = (Y != 0).mean(axis=1) >= cfg.donor_min_nonzero_share
        self.donor_ok = usable & nonzero
        total = Y[usable].sum()
        self.share = Y.sum(axis=1) / total if total > 0 else np.zeros(len(Y))
        self.national = Y[usable].sum(axis=0)
        self.revenue = panel.kpis["revenue"][:, self.cols] if "revenue" in panel.kpis and cfg.kpi == "orders" else None
        self.orders = panel.kpis["orders"][:, self.cols] if "orders" in panel.kpis else None
        eligible = usable & nonzero & np.array([g not in cfg.not_eligible for g in panel.geos])
        eligible &= self.share <= cfg.share_max / 2      # no single market may dominate a cell
        self.eligible = np.nonzero(eligible)[0]
        self.pop = None
        if cfg.population:
            self.pop = np.array([float(cfg.population.get(g, np.nan)) for g in panel.geos])
        self.strata = self._strata()

    # -- candidate generation (§9.2) -------------------------------------------------
    @property
    def n_pick(self) -> int:
        """Markets drawn per stratum: one per cell, or one for the holdout in a national holdout."""
        return 1 if self.cfg.holdout else self.cfg.n_cells

    def _strata(self) -> list[np.ndarray]:
        k1 = self.n_pick + 1
        order = self.eligible[np.argsort(-self.share[self.eligible], kind="stable")]
        return [order[i:i + k1] for i in range(0, len(order) - k1 + 1, k1)]

    def candidates(self, rng: np.random.Generator) -> list[tuple[list[np.ndarray], float]]:
        cfg = self.cfg
        out, seen = [], set()
        attempts = 0
        while len(out) < cfg.n_candidates and attempts < cfg.n_candidates * 3:
            attempts += 1
            target = rng.uniform(cfg.share_min, cfg.share_max)
            cells = [[] for _ in range(self.n_pick)]
            shares = np.zeros(self.n_pick)
            for s in rng.permutation(len(self.strata)):
                stratum = self.strata[s]
                if np.any(shares + self.share[stratum].max() > cfg.share_max):
                    continue
                pick = rng.permutation(stratum)[: self.n_pick]
                for c, g in enumerate(pick):
                    cells[c].append(g)
                    shares[c] += self.share[g]
                if shares.min() >= target:
                    break
            if shares.min() < max(target, cfg.share_min):
                continue
            key = tuple(tuple(sorted(c)) for c in cells)
            if key in seen:
                continue
            seen.add(key)
            out.append(([np.array(sorted(c)) for c in cells], float(target)))
        return out

    # -- scoring (§9.3) ------------------------------------------------------------
    def features(self, rows: np.ndarray) -> dict:
        agg = self.Y[rows].sum(axis=0)
        first, last = agg[:TREND_DAYS].sum(), agg[-TREND_DAYS:].sum()
        f = {
            "share": float(self.share[rows].sum()),
            "trend": float(last / first) if first > 0 else np.nan,
            "seasonality": float(np.corrcoef(agg, self.national)[0, 1]) if agg.std() > 0 else np.nan,
        }
        if self.pop is not None and not np.isnan(self.pop[rows]).any():
            f["population"] = float(self.pop[rows].sum())
        if self.revenue is not None and self.orders is not None:
            o = self.orders[rows].sum()
            f["aov"] = float(self.revenue[rows].sum() / o) if o > 0 else np.nan
        return f

    def rest_of(self, rows: np.ndarray) -> np.ndarray:
        """Every usable market not in `rows`: the campaign's markets in a national holdout (§13.2)."""
        return np.setdiff1d(np.nonzero(np.array([g not in self.cfg.excluded for g in self.geos]))[0], rows)

    def split(self, rows: np.ndarray, rng: np.random.Generator) -> list[np.ndarray]:
        """Split markets between the cells (§13.7), largest first. Each market goes to the cell that is smallest so far,
        measured by the larger of its share of sales and (when known) its share of population, so sales per person stay
        even too; cells within half that market's size of the smallest are equally likely, so the search still explores.
        Markets a vendor can't target (not_eligible) get no one's ads, so they are left out of every cell."""
        k = self.cfg.n_cells
        ok = np.array([self.geos[r] not in self.cfg.not_eligible for r in rows], bool)
        order = rows[ok][np.argsort(-self.share[rows[ok]], kind="stable")]
        pop = None
        if self.pop is not None and not np.isnan(self.pop[order]).any():
            pop = self.pop / self.pop[order].sum() * self.share[order].sum()   # population on the same scale as sales
        cells, sales, people = [[] for _ in range(k)], np.zeros(k), np.zeros(k)
        for g in order:
            size = max(self.share[g], pop[g]) if pop is not None else self.share[g]
            load = np.maximum(sales, people) if pop is not None else sales
            c = int(rng.choice(np.nonzero(load <= load.min() + 0.5 * size)[0]))
            cells[c].append(g)
            sales[c] += self.share[g]
            if pop is not None:
                people[c] += pop[g]
        return [np.array(sorted(c), dtype=int) for c in cells]

    def describe(self, cell_rows: list[np.ndarray], target: float, control_rows: np.ndarray | None = None) -> Design:
        in_cells = np.concatenate(cell_rows)
        control = self.rest_of(in_cells) if control_rows is None else control_rows
        feats = [self.features(r) for r in cell_rows]
        if self.cfg.holdout and len(cell_rows) > 1:
            # Cells vs each other (size and shape), and the holdout vs all markets with ads (shape only), §13.7
            per_cap = lambda r: float(self.Y[r].sum() / self.pop[r].sum())
            have_pop = self.pop is not None and not np.isnan(self.pop).any()
            feats = [{k: v for k, v in f.items() if k not in ("population", "seasonality")} for f in feats]
            if have_pop:
                for f, r in zip(feats, cell_rows):
                    f["per_capita"] = per_cap(r)
            balance = {k: relative_gap([f[k] for f in feats]) for k in feats[0] if all(k in f for f in feats)}
            hf, af = self.features(control), self.features(in_cells)
            pairs = {k: (hf[k], af[k]) for k in ("trend", "aov") if k in hf and k in af}
            if have_pop:
                pairs["per_capita"] = (per_cap(control), per_cap(in_cells))
            balance.update({f"holdout_{k}": relative_gap(v) for k, v in pairs.items()})
        elif self.cfg.holdout:
            # Holdout vs everyone else: compare the shape of sales, not size. Correlation with the national series
            # is left out: the cell nearly *is* the nation, so the gap measures the holdout's noise, which the fit gate covers (§13.2).
            feats = [{k: v for k, v in f.items() if k not in ("share", "population", "seasonality")}
                     for f in (feats[0], self.features(control))]
            if self.pop is not None and not np.isnan(self.pop).any():
                for f, r in zip(feats, (cell_rows[0], control)):
                    f["per_capita"] = float(self.Y[r].sum() / self.pop[r].sum())
        if not (self.cfg.holdout and len(cell_rows) > 1):
            balance = {k: relative_gap([f[k] for f in feats]) for k in feats[0] if all(k in f for f in feats)}
        return Design(
            cells=[sorted(self.geos[r].tolist()) for r in cell_rows],
            control=sorted(self.geos[control].tolist()),
            shares=[float(self.share[r].sum()) for r in cell_rows],
            control_share=float(self.share[control].sum()),
            balance=balance, balance_score=max(balance.values()) if balance else 0.0, target_share=target,
        )

    def holdout_fit(self, cell_rows: list[np.ndarray], augment: bool, control_rows: np.ndarray | None = None,
                    in_sample: bool = False) -> list[float]:
        """Fit on the pre-period minus its last test_days, forecast those days, nRMSE per cell (§9.3).

        in_sample=True instead fits the whole pre-period and scores it, as the Read module's pre-period fit check does."""
        h = 0 if in_sample else self.cfg.test_days
        n_fit = self.Y.shape[1] - h
        in_cells = np.zeros(len(self.geos), bool)
        in_cells[np.concatenate(cell_rows)] = True
        donors = np.nonzero(self.donor_ok & ~in_cells)[0]
        if self.cfg.holdout:
            # One twin of the holdout per cell, built from that cell's markets, on indexed series (§13.3, §13.7)
            held = self.rest_of(np.concatenate(cell_rows)) if control_rows is None else control_rows
            out = []
            for rows in cell_rows:
                y1, Y0 = index_rows(self.Y, held, rows[self.donor_ok[rows]], n_fit)
                fit = ascm.fit(y1, Y0, n_fit, augment=augment)
                r = (y1 - fit.counterfactual)[n_fit:] if h else (y1 - fit.counterfactual)
                out.append(float(np.sqrt(np.mean(r**2)) / y1[:n_fit].mean()))
            return out
        out = []
        for rows in cell_rows:
            y1 = self.Y[rows].mean(axis=0)
            fit = ascm.fit(y1, self.Y[donors], n_fit, augment=augment)
            r = (y1 - fit.counterfactual)[n_fit:] if h else (y1 - fit.counterfactual)
            level = y1[:n_fit].mean()
            out.append(float(np.sqrt(np.mean(r**2)) / level) if level > 0 else float("inf"))
        return out

    def run(self, progress=None) -> dict:
        """Search, gate and score. Returns the shortlist plus counts for the funnel shown in the UI."""
        cfg = self.cfg
        rng = np.random.default_rng(cfg.seed)
        cands = self.candidates(rng)
        funnel = {"strata": len(self.strata), "eligible_geos": int(len(self.eligible)), "generated": len(cands)}
        gated = []
        for rows, target in cands:
            held = None
            if cfg.holdout:
                held = rows[0]
                rows = [self.rest_of(held)] if cfg.n_cells == 1 else self.split(self.rest_of(held), rng)
                d = self.describe(rows, target, held)
                ok = (cfg.share_min <= d.control_share <= cfg.share_max and len(d.control) >= cfg.min_holdout_geos
                      and all(len(r) >= cfg.min_holdout_geos for r in rows))
            else:
                d = self.describe(rows, target)
                ok = all(cfg.share_min <= s <= cfg.share_max for s in d.shares) and d.control_share >= cfg.min_control_share
            if ok and d.balance_score <= cfg.balance_max:
                gated.append((rows, d, held))
        funnel["passed_share_and_balance"] = len(gated)

        for i, (rows, d, held) in enumerate(gated):
            d.fit_screen = self.holdout_fit(rows, augment=False, control_rows=held)
            if progress and i % 25 == 0:
                progress({"stage": "screen", "done": i, "total": len(gated)})
        gated.sort(key=lambda g: (max(g[1].fit_screen), g[1].balance_score))
        top = gated[: cfg.screen_top]
        for i, (rows, d, held) in enumerate(top):
            d.fit = self.holdout_fit(rows, augment=True, control_rows=held)
            if progress:
                progress({"stage": "fit", "done": i + 1, "total": len(top)})
        passing = [(rows, d, held) for rows, d, held in top if max(d.fit) <= cfg.fit_max]
        funnel["scored_full_fit"] = len(top)
        funnel["passed_fit"] = len(passing)
        passing.sort(key=lambda g: (max(g[1].fit), g[1].balance_score))
        for rows, d, held in passing[: cfg.shortlist]:
            d.pre_fit = self.holdout_fit(rows, augment=True, control_rows=held, in_sample=True)
        return {"designs": [d for _, d, _ in passing[: cfg.shortlist]], "funnel": funnel,
                "best_failing": sorted((d for _, d, _ in top), key=lambda d: max(d.fit))[:3] if not passing else []}
