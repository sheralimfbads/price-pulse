# PricePulse Project Guide: What, Why, and How

This guide records the project's design and the reasoning behind the first working local pipeline. It is intended as a learning notebook you can return to after a break.

## 1. The business question

PricePulse starts with official monthly average prices for selected goods in Uzbekistan. The initial dataset is not store-level price comparison: it represents an official average price for a homogeneous commodity category, with values expressed in soums per kilogram.

Questions the processed dataset can answer include:

- How did a product's price change from the previous month?
- How does a price compare with the same month one year earlier?
- Which products saw the largest percentage increases or decreases?
- Is the data complete, unique, valid, and traceable to a source snapshot?

The first version deliberately starts with one reliable source. Additional permitted sources can be added later without changing the core purpose of the pipeline.

## 2. Source inspection and ingestion

The source endpoint returns a JSON list containing one dataset object with two important keys:

- `metadata`: 17 metadata items in the inspected snapshot.
- `data`: 41 product records.

Each product record contains a code, product names in multiple languages, and monthly prices stored in separate fields. The month labels are not completely uniform: for example, `2021-М01` uses a Cyrillic letter that looks like Latin `M`, while later fields may use `2022-M01`.

### Why preserve a raw snapshot?

A raw snapshot gives us a reproducible input for debugging. If normalization logic changes, we can run it against the same source file without depending on the endpoint being available or unchanged. A timestamp in the file name indicates when PricePulse fetched the dataset; it is not the date of a price observation.

### Request safety

The HTTP request uses a timeout and checks the status code. These choices prevent indefinitely waiting for a response and prevent silently treating HTTP error responses as successful downloads. The JSON structure is validated before later code relies on it.

### Diagnostic vs. extraction responsibilities

The early `inspect_source.py` version downloaded data and printed its metadata and sample records. As the project matures, extraction should save the raw snapshot and emit concise operational logs, while inspection should read an existing snapshot and print diagnostic details only when requested.

## 3. Normalization: wide data to long data

The original data is wide-format: one product per row, with one price column per month. This is convenient for reading a table but awkward for SQL analysis because adding a month adds another column.

The normalized data is long-format: one row per product-month. Its core fields are:

- `product_code`: source identifier stored as text to preserve leading zeros, such as `001`.
- Four product-name fields.
- `period`: the first day of the month, represented as an ISO date such as `2026-09-01`.
- `average_price_uzs_per_kg`: source-provided numerical value before the analytical cleaning rule.
- `source_fetched_at_utc`: snapshot fetch time.
- `source_snapshot`: the raw file that the row came from.

The month parser extracts numeric year and month components rather than depending on the Latin/Cyrillic separator character. The transformation checks product codes, detects repeated periods, sorts periods chronologically, and writes a CSV.

### Observed result

- 41 products.
- 69 monthly periods, January 2021 through September 2026.
- 2,829 rows (`41 × 69`).
- No missing monthly fields in the source records inspected by that transformation.

The count is a sanity check, not proof of data correctness. Separate audit checks are required.

## 4. Data quality audit

The pandas audit examines:

- Expected column names.
- Invalid or missing dates.
- Missing product identifiers.
- Duplicate `(product_code, period)` keys.
- Missing, non-numeric, negative, or zero prices.
- Overall monthly timeline gaps.
- Missing product-month combinations.
- Number of observations per product.

The audit found 2,829 unique product-month keys, 41 product codes, 69 periods, and no missing month in the overall timeline. Each product had 69 rows. Six source prices were zero.

### What does a passing audit mean?

It means the defined checks passed. It does not prove that each reported price is factually correct. Data quality rules should be explicit, appropriate for the source, and tested as the project evolves.

## 5. Investigation and analytical cleaning

The six zero values were traced back to the raw JSON. The values matched exactly, so normalization did not create them. Five were watermelon observations (March–April 2025 and February–April 2026), and one was melon (April 2021).

The source metadata mentions seasonal unavailability for some fruits and vegetables, but the inspected metadata does not explicitly define zero as a missing-value marker. Therefore the project uses a documented **working assumption**: zero is marked unavailable for analysis.

The cleaning output preserves two concepts:

- `source_price_uzs_per_kg`: the value received from the source, including zero.
- `average_price_uzs_per_kg`: the analytical value; under the current rule, zero becomes missing (`NULL` when loaded into PostgreSQL).

`price_status` makes the treatment explicit:

- `observed`: a positive analytical price is available.
- `zero_marked_unavailable`: the source value is zero and the analytical price is missing.
- `missing_in_source`: reserved for a genuinely missing source value.

In the observed data, the cleaner produced 2,823 `observed` records and 6 `zero_marked_unavailable` records, retaining 2,829 total rows.

### Why not delete those six rows?

A price observation and a price measurement are different things. We still know that the product-month observation exists, even if it has no usable analytical price. Preserving the row and its status keeps completeness and measurement availability distinguishable.

## 6. Automated tests

The cleaning tests cover these behaviors:

1. A positive price is preserved.
2. A zero remains in the source-price field but becomes missing analytically.
3. A missing price stays missing.
4. A malformed price raises an error.
5. A negative price raises an error.

The five cleaning tests were confirmed passing. Orchestration tests for the runner were subsequently proposed; confirm they have been added and are passing before documenting a seven-test total as current fact.

Run tests with:

```bash
python -m pytest -q
```

Small, isolated unit tests do not need network access or a live PostgreSQL server. Future integration tests should exercise database loading against a controlled test database or disposable instance.

## 7. PostgreSQL staging layer

The first PostgreSQL table is `staging.official_price_observations`. It keeps the normalized columns, source values, analytic values, statuses, fetch timestamps, and source snapshot names.

The table's primary key is `(product_code, period)`. That prevents two staging rows for the same product and month. Check constraints validate month-start dates, non-negative prices, allowed status values, and consistency between status and source/analytical price fields.

The staging table preserves a straightforward relationship to the normalized input. The later analytics model separates repeated descriptive attributes from price measurements.

## 8. Analytical SQL

### Month-over-month change

`LAG(price) OVER (PARTITION BY product_code ORDER BY period)` gets the preceding observation for each product. The change is current minus previous; the percentage change divides that difference by the previous price. `NULLIF(previous_price, 0)` makes a zero denominator yield `NULL` rather than division-by-zero failure.

### Year-over-year comparison

`LAG(price, 12)` looks twelve rows back within each product's ordered history. It aligns to the same month of the previous year only while each product has complete, consistently ordered monthly rows. If rows can be missing, match on a calendar date or join to the same period one year earlier.

### Ranking

`RANK()` sorts a set of products by a metric such as year-over-year percentage change. Equal metric values receive equal ranks, and subsequent ranks can have gaps.

### CTEs

A `WITH` clause defines common table expressions (CTEs), making a multi-stage analytical query easier to read: calculate history, filter to the latest month, then rank the results.

## 9. Query plans and indexes

The staging primary key creates a B-tree index on `(product_code, period)`.

Observed plan for Rice history:

- `Index Scan Backward` using the primary-key index.
- Returned 12 rows.
- Approximately 0.061 ms execution time in one local run.

Observed plan filtering all products from January 2026 onward:

- `Seq Scan` followed by a sort.
- Scanned 2,829 rows and retained 369.
- Approximately 0.711 ms execution time in one local run.

These timings are a demonstration, not a reliable benchmark. The table is small and cached data, environment load, and other conditions affect them. A sequential scan can be optimal for small tables or broad queries. Don't create indexes solely to eliminate every sequential scan.

## 10. Star schema

The analytics model contains:

- `analytics.dim_product`: one row per source product, with multilingual names.
- `analytics.dim_month`: one row per month, with `month_key` in `YYYYMM` form plus year, quarter, and month attributes.
- `analytics.fact_monthly_official_price`: one row per product-month with price measurements, status, and source provenance.

The fact table uses foreign keys to both dimensions and a composite primary key `(product_key, month_key)`. In the verified dataset, there are 41 product rows, 69 month rows, and 2,829 fact rows.

The dimensional model reduces repetition of descriptive product/calendar attributes and makes analytical joins explicit. The staging layer remains available to support reconciliation and debugging.

## 11. Python loader and transaction

`scripts/load_to_postgres.py` uses Psycopg 3. It streams the analytical CSV with PostgreSQL `COPY` into a temporary table, rejects duplicate product-month keys, and checks that normalization produced the registered product-by-month grid. The latest accepted snapshot is authoritative: the loader upserts included rows and removes omitted observations and orphaned dimensions.

The loader serializes concurrent runs, rejects snapshots older than the current live snapshot, and applies reconciliation within one transaction. If an error escapes before commit, the transaction rolls back rather than leaving a partially updated set of tables. Raw snapshots and their registry entries preserve replay/audit evidence; current facts do not preserve prior value versions.

The loader requests the database password at runtime instead of embedding a credential in source code. Snapshot registry count checks catch partial normalization, but they cannot prove that the publisher's response itself is complete.

## 12. Local pipeline runner

`scripts/run_pipeline.py` uses `subprocess.run(..., check=True)` to invoke each step in sequence. If a step exits non-zero, the runner stops and propagates its exit code instead of running later steps with potentially stale intermediate data.

A deliberate failure test using a nonexistent normalization script produced exit code `2` and stopped before cleaning/testing/loading. The correct script path was then restored and the full pipeline ran successfully.

The runner is a simple sequential orchestrator. It is not a replacement for Airflow: it does not provide a scheduler, task-level retry policy, run history, UI, or native backfills.

## 13. What to learn next

1. Finish logging and automated integration testing.
2. Make runs safer and more observable; consider avoiding writes to unchanged database records.
3. Containerize Python and PostgreSQL dependencies with Docker Compose.
4. Orchestrate the stages in an Airflow DAG with dependencies, retries, scheduling, and backfills.
5. Add dbt for documented, modular analytical SQL models and tests.
6. Add one cloud platform after the local system is reproducible.
7. Explore Spark, table formats, and streaming only after core batch pipeline behavior is robust.
