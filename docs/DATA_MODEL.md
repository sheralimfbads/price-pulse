# PricePulse Data Model Reference

## Layers

### Raw

`data/raw/official_prices_<UTC timestamp>.json` stores a downloaded source response. Raw snapshots are debugging and lineage artifacts and should not be modified by transformation code.

### Processed normalized CSV

`data/processed/official_prices_long.csv` contains one row per product-month:

| Column | Meaning |
|---|---|
| `product_code` | Source product code stored as text, preserving leading zeros |
| `product_name_uz` | Product name in Uzbek Latin script |
| `product_name_ru` | Product name in Russian |
| `product_name_en` | Product name in English |
| `product_name_uz_cyrillic` | Product name in Uzbek Cyrillic script |
| `period` | First day of the observation month |
| `average_price_uzs_per_kg` | Source-provided price value before the cleaning policy |
| `source_fetched_at_utc` | When this snapshot was downloaded |
| `source_snapshot` | Raw file name used to produce the row |

### Processed analytical CSV

`data/processed/official_prices_analytics.csv` preserves source values and adds:

| Column | Meaning |
|---|---|
| `source_price_uzs_per_kg` | Source price, including a source zero |
| `average_price_uzs_per_kg` | Analytical price; zero is currently mapped to missing under the documented project assumption |
| `price_status` | `observed`, `zero_marked_unavailable`, or `missing_in_source` |

### PostgreSQL staging

`staging.official_price_observations` mirrors the normalized/analytical row structure and enforces `(product_code, period)` uniqueness.

### PostgreSQL analytics star schema

#### `analytics.dim_product`

- `product_key`: generated surrogate primary key.
- `product_code`: source code, unique.
- Four multilingual product-name columns.

#### `analytics.dim_month`

- `month_key`: integer `YYYYMM` key (example: September 2026 is `202609`).
- `month_start`: first day of the month.
- `calendar_year`, `quarter_number`, `month_number`: calendar attributes.

#### `analytics.fact_monthly_official_price`

- `product_key`: foreign key to `dim_product`.
- `month_key`: foreign key to `dim_month`.
- `source_price_uzs_per_kg`: original measurement.
- `average_price_uzs_per_kg`: analytical measurement.
- `price_status`: explicit interpretation of availability.
- `source_fetched_at_utc`, `source_snapshot`: source lineage.
- Primary key: `(product_key, month_key)`.

## Grain and key decisions

The grain of the fact table is **one official monthly price observation for one product**. The composite primary key enforces this grain in the current model. If new sources later have store-specific, regional, or unit-specific prices, those dimensions will change the grain and the key must be redesigned explicitly.

## Useful validation queries

```sql
-- Expected row counts
SELECT 'dim_product' AS table_name, COUNT(*) FROM analytics.dim_product
UNION ALL
SELECT 'dim_month', COUNT(*) FROM analytics.dim_month
UNION ALL
SELECT 'fact_monthly_official_price', COUNT(*)
FROM analytics.fact_monthly_official_price;

-- Availability profile
SELECT price_status, COUNT(*) AS rows,
       COUNT(average_price_uzs_per_kg) AS analytical_prices_available
FROM analytics.fact_monthly_official_price
GROUP BY price_status
ORDER BY price_status;

-- Recent price history for Rice
SELECT p.product_code, p.product_name_en, m.month_start,
       f.source_price_uzs_per_kg, f.average_price_uzs_per_kg,
       f.price_status
FROM analytics.fact_monthly_official_price AS f
JOIN analytics.dim_product AS p ON p.product_key = f.product_key
JOIN analytics.dim_month AS m ON m.month_key = f.month_key
WHERE p.product_code = '001'
ORDER BY m.month_start DESC
LIMIT 12;
```
