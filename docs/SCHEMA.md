# FOSIT Data Schemas

**Status:** v1 draft for review.

> **In plain English:** FOSIT needs at most three simple spreadsheets (CSV files): your sales by market and day, what each vendor spent and where, and (optionally) your own market list. Everything is checked in your browser. If something's wrong, we tell you exactly which row and how to fix it.

Machine-readable specs live in [`/schema`](../schema). CSV files use the [Frictionless Table Schema](https://specs.frictionlessdata.io/table-schema/) format (an open standard, no library needed to read it). The locked plan uses [JSON Schema 2020-12](https://json-schema.org/). Rules a table schema can't express (marked **cross-field** below) are enforced in Python inside `core/fosit` (`panel.py` for KPI history). The browser (Pyodide), the CI tests and the command-line validator `schema/validate.py` all run that same code. Spend & delivery and locked-plan validators ship with the Read module.

**General CSV rules (all files):** UTF-8 (BOM tolerated), comma-delimited, header row required, column names case-insensitive with surrounding spaces trimmed, extra columns ignored (and listed), empty cell = missing. Dates are `YYYY-MM-DD`.

**Severity:** ❌ **error**: we stop and explain the fix. ⚠️ **warning**: we continue, show it, and include it in the report.

---

## 1. KPI history: `kpi_history.csv`

Spec: [`schema/kpi_history.table.json`](../schema/kpi_history.table.json). Used by **Plan** (history) and **Read** (history through the end of cooldown).

| Column | Type | Required | Meaning |
|---|---|---|---|
| `date` | date | ✓ | Day, in your reporting time zone |
| `geo_id` | string | ✓ | Market ID in the chosen geo unit (CBSA code like `35620`, state like `NY`, or your own mapping's ID) |
| `orders` | number ≥ 0 | one of these | Orders or conversions |
| `revenue` | number | one of these | Revenue in the plan currency |

```csv
date,geo_id,orders,revenue
2026-06-01,35620,412,38211.50
2026-06-01,31080,298,27002.10
2026-06-02,35620,397,36940.00
```

Rules:

| Rule | Severity |
|---|---|
| At least one of `orders`, `revenue` present (**cross-field**) | ❌ |
| `(date, geo_id)` unique | ❌ (duplicates listed) |
| A date missing for **every** geo inside the range (data gap) | ❌ |
| Missing `(date, geo)` rows for a geo that appears elsewhere → filled with 0, count reported | ⚠️ |
| Pre-period < 8 weeks | ⚠️ (12+ recommended) |
| `geo_id` not found in the geo unit's list | ⚠️ (rows excluded, listed) |
| Negative `revenue` | ⚠️ |
| `orders` not a whole number | ⚠️ (allowed, e.g. modelled conversions) |
| Read only: data ends before `cooldown_end` | ⚠️ → report marked **INTERIM** |

## 2. Order-level export helper: `orders_export.csv`

Spec: [`schema/orders_export.table.json`](../schema/orders_export.table.json). For users who only have a raw order export. FOSIT aggregates it to KPI history **in the browser**.

| Column | Type | Required | Meaning |
|---|---|---|---|
| `order_date` | `YYYY-MM-DD` or ISO timestamp | ✓ | Only the date part is used, as written (no time-zone conversion) |
| `shipping_zip` | ZIP / ZIP+4 | ✓ | Mapped to `geo_id` via the crosswalk |
| `revenue` | number | | Order revenue |
| `order_id` | string | | If present, duplicates are dropped |

Rules: 3–4 digit ZIPs are left-padded with zeros (spreadsheets strip them) ⚠️. Unmapped ZIPs are counted, with the share of orders affected ⚠️, or ❌ if more than 10% of orders. Duplicate `order_id` ⚠️.

## 3. Spend and delivery: `spend_delivery.csv`

Spec: [`schema/spend_delivery.table.json`](../schema/spend_delivery.table.json). Used by **Read**. Each vendor typically sends its own rows. The advertiser stacks them into one file.

| Column | Type | Required | Meaning |
|---|---|---|---|
| `date` | date | ✓ | Delivery day |
| `cell` | string | ✓ | Cell **label or id** exactly as in the locked plan |
| `geo_id` | string or `*` | ✓ | Where impressions were delivered, in the plan's geo unit. `*` = not attributable to a geo |
| `impressions` | integer ≥ 0 | ✓ | |
| `spend` | number ≥ 0 | ✓ | Media cost in the plan currency |

```csv
date,cell,geo_id,impressions,spend
2026-09-01,Cell 1,35620,182000,4100.00
2026-09-01,Cell 1,31080,1200,27.00
2026-09-01,Cell 2,*,0,3950.00
2026-09-01,Cell 2,19100,171500,0
```

Rules:

| Rule | Severity |
|---|---|
| `cell` not in plan (**cross-field**) | ❌ |
| `(date, cell, geo_id)` unique | ❌ |
| Rows dated outside `[test_start, cooldown_end]` | ⚠️ (excluded from spend, listed) |
| Impressions in geos outside the cell's list → **leakage** (see METHODOLOGY §11) | ⚠️ if > 5% |
| `geo_id = *` impressions → **unverifiable**, shown separately (not counted as leakage) | ⚠️ if > 5% |
| Vendor reports ZIPs or DMAs instead of the plan's unit → use the mapping helper first | ❌ until mapped |

## 4. Geo mapping (optional): `geo_mapping.csv`

Spec: [`schema/geo_mapping.table.json`](../schema/geo_mapping.table.json). Your own `zip → geo_id` mapping, e.g. an internal DMA list. FOSIT doesn't ship Nielsen DMA definitions because they're proprietary. The file's SHA-256 is locked in the plan.

| Column | Required |
|---|---|
| `zip` (5 digits) | ✓ |
| `geo_id` | ✓ |
| `geo_name` | |

Each ZIP maps to exactly one geo ❌.

## 5. Geo attributes: `geo_attributes.csv`

Spec: [`schema/geo_attributes.table.json`](../schema/geo_attributes.table.json). **Shipped** for CBSA and state units (Census population estimates, vintage recorded in the file header). Optional for custom units. Without population, the population balance metric is skipped and the report says so.

| Column | Required | Meaning |
|---|---|---|
| `geo_id` | ✓ | |
| `geo_name` | ✓ | |
| `state` | | Principal state |
| `population` | | Used for balance |
| `treatment_eligible` | | `false` for units vendors can't target cleanly (default: `{STATE}-NONCBSA`) |

## 6. Locked plan: `*.fosit-plan.json`

Spec: [`schema/locked_plan.schema.json`](../schema/locked_plan.schema.json). How it's hashed and shared: [PREREGISTRATION.md](PREREGISTRATION.md).

Structure:

```jsonc
{
  "fosit_plan_version": "1.0",
  "commitment": {             // ← hashed. Everything that decides the answer.
    "tool": {...}, "created_at": "...", "test_name": "...", "currency": "USD",
    "geo": {...}, "kpi": {...}, "dates": {...}, "design": {...},
    "cells": [{ "id": "cell_1", "label": "...", "geo_ids": [...], "budget": 50000 }, ...],
    "control": {...}, "excluded": {...},
    "method": {...}, "thresholds": {...}, "decision": {...},
    "assignment": {...}, "vendor_targeting_confirmed": [...], "data_fingerprint": {...}
  },
  "hash": { "algorithm": "SHA-256", "canonicalization": "RFC8785", "value": "9f2c…" },
  "appendix": { ... }         // ← NOT hashed. Diagnostics. Safe to delete before sending.
}
```

**Cross-field rules** (❌ unless noted):

- `pre_start < pre_end < test_start ≤ test_end ≤ cooldown_end`. Pre-period < 56 days ⚠️.
- `design.type` is `crossover` for the small-advertiser design ([METHODOLOGY §14](METHODOLOGY.md#14-geo-crossover-for-small-advertisers)): one cell (half A), `control.geo_ids` is half B, and `design.block_days`, `design.washout_days` and `design.schedule` (one `A`/`B` per block, each half in half the blocks) are required; `cooldown_end` equals `test_end`, and the method is `crossover_twfe` with `randomization` inference.
- `design.type` is `geo_cells` (default when absent) or `national_holdout` ([METHODOLOGY §13](METHODOLOGY.md#13-national-holdout)). A national holdout has one or more cells: with one, the cell is every market with the campaign; with several, vendors split those markets ([METHODOLOGY §13.7](METHODOLOGY.md#137-several-vendors-split-the-country)). Its `control.geo_ids` are the holdout markets, and `design.ads_before_test` (`off` or `always_on`) is required.
- Cell `geo_ids`, `control.geo_ids`, and `excluded.geo_ids` are pairwise **disjoint**.
- All geo lists sorted ascending (code-point order), so the canonical form is unique.
- Every number in `commitment` is an integer or a decimal with absolute value in [0.0001, 1e15), so standard JSON libraries reproduce the RFC 8785 hash ([PREREGISTRATION.md](PREREGISTRATION.md)).
- Cell ids are `cell_1..cell_K`. Labels are unique.
- `vendor_targeting_confirmed` has one `confirmed: true` entry per cell.
- `method.lambda_value` present iff `lambda_selection = "fixed"`.
- `method.placebo_calibration` (`{"n": 40}` in plans from the current Plan module) turns on placebo calibration ([METHODOLOGY §5.6](METHODOLOGY.md#56-placebo-calibration)). Plans without it are read with plain conformal ranges, exactly as they were locked.
- `decision.target_icpa` present iff basis is `target_icpa`. Same for `breakeven_iroas`.
- `decision.planned_mde_lift` (cell id → planned minimum detectable lift) is written by the current Plan module. For older plans, Read falls back to the planned MDE in the (unhashed) appendix.
- `kpi.primary` must exist in the planning data.
- `thresholds.pre_fit_nrmse_max` has an entry for every cell × KPI analysed. `thresholds.pre_fit_period` (`day`, the default when absent, or `week`) says whether that limit applies day by day or to weekly totals ([METHODOLOGY §9.3](METHODOLOGY.md#93-scoring)).

## 7. Outputs

- **Results CSV:** [`schema/results.table.json`](../schema/results.table.json). Long format, one row per (cell or head-to-head pair) × KPI × metric, with 90%/95% bounds. Empty bounds mean unbounded or not defined, and the `note` column explains which. Every row carries `plan_hash` and a `method_ref` anchor into METHODOLOGY.md.
- **Analysis config:** `*.fosit-analysis.json`. The locked plan + SHA-256 of every input file + FOSIT version + all run parameters, so anyone with the same files can reproduce the report bit-for-bit.
- **Report PDF:** generated in the browser. Contains every honesty check, every verdict, and the plan hash on every page.
