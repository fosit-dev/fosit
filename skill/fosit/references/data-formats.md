# FOSIT data formats

Read this when preparing or fixing input files. All files are CSV, UTF-8, with a header row; column names are case-insensitive; extra columns are ignored; dates are `YYYY-MM-DD`. Full spec: `docs/SCHEMA.md` in the FOSIT repository.

## Daily sales by market (`check`, `plan`, `read --sales`)

| Column | Required | Meaning |
|---|---|---|
| `date` | yes | day, in the advertiser's reporting time zone |
| `geo_id` | yes | market ID in the chosen unit: CBSA code like `35620`, state like `NY`, or their own ID |
| `orders` | one of these | orders or conversions |
| `revenue` | one of these | revenue in the plan currency |

```csv
date,geo_id,orders,revenue
2026-06-01,35620,412,38211.50
2026-06-01,31080,298,27002.10
```

Common problems the `check` command reports, and the fix:
- **Duplicate (date, geo_id) rows** → sum them before loading.
- **A whole day missing for every market** → a data gap; fill it from the source system (FOSIT won't guess).
- **Missing days for a small market** → filled with 0 and reported; normal for tiny markets.
- **Unknown geo IDs** → wrong unit (e.g. DMA codes with `--unit cbsa`) or typos; those rows are dropped and listed.
- **Under 8 weeks of history** → plans are unreliable; get more history.
- For reading, the file must run **through the end of the cooldown** and still include the plan's history period.

## Order export (`orders`)

For advertisers who only have order-level data. FOSIT maps ZIPs to markets and adds up by day, locally.

| Column | Required | Meaning |
|---|---|---|
| `order_date` | yes | date or ISO timestamp (only the date part is used, no time-zone conversion) |
| `shipping_zip` | yes | 5-digit ZIP or ZIP+4 (3–4 digit ZIPs from spreadsheets are re-padded) |
| `revenue` | no | order revenue |
| `order_id` | no | duplicates are dropped |

More than 10% of orders with unmappable ZIPs is an error. With `--unit custom`, pass `--mapping` with columns `zip,geo_id[,geo_name]` (one market per ZIP).

## Spend & delivery (`read --spend`)

One file with every vendor's rows (each vendor usually sends its own; stack them).

| Column | Meaning |
|---|---|
| `date` | delivery day |
| `cell` | the vendor/cell **label exactly as in the plan** (or `cell_1`, `cell_2`…) |
| `geo_id` | market where impressions were delivered, in the plan's unit; `*` = not attributable |
| `impressions` | integer ≥ 0 |
| `spend` | media cost in the plan currency |

```csv
date,cell,geo_id,impressions,spend
2026-09-01,Vendor A,35620,182000,4100.00
2026-09-01,Vendor B,*,0,3950.00
```

Rows outside the test-plus-cooldown window are left out and reported. Impressions in control or held-out markets count as **leakage** (pushes measured lift toward zero); `*` rows are "unverifiable". If a vendor reports by ZIP or DMA instead of the plan's unit, map them first.

## Getting the data from common places
- **Shopify / ecommerce:** export orders with shipping ZIP → `orders` command.
- **Data warehouse:** `SELECT order_date AS date, <market> AS geo_id, COUNT(*) AS orders, SUM(revenue) AS revenue … GROUP BY 1, 2`.
- **Vendors:** ask each for daily impressions and spend by market (state, metro or ZIP), for the test and cooldown.
