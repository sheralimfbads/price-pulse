# Decisions, Assumptions, and Known Limitations

This document prevents an implementation choice from quietly turning into an unexamined “fact.” Revisit these decisions when the source or project requirements change.

## D001 — Preserve raw JSON snapshots

**Decision:** Keep timestamped raw source snapshots locally and transform copies of those values into processed datasets.

**Why:** Enables reproducible transformations, source-to-output investigation, and audit trails.

**Limitation:** Local snapshots are not yet a managed archive or a guaranteed backup. They are intentionally excluded from Git by the current ignore rules.

## D002 — Normalize the source into one row per product-month

**Decision:** Convert the source's monthly columns into a long table keyed by product code and period.

**Why:** It makes filtering, aggregation, joins, and window functions straightforward.

**Invariant:** There should be at most one row per `(product_code, period)` in the normalized snapshot.

## D003 — Treat source zero prices as unavailable in the analytical layer

**Evidence:** Six zero values exist in the source itself: five watermelon rows and one melon row. The source metadata mentions seasonal unavailability of some fruit and vegetable prices.

**Decision:** Preserve zero in `source_price_uzs_per_kg`, set the analytical price to missing, and label the row `zero_marked_unavailable`.

**Important uncertainty:** The inspected metadata does not explicitly state that zero is the source's missing-value marker. This remains a documented project assumption, not a confirmed official encoding rule. Revisit it if authoritative source documentation becomes available.

## D004 — Product codes are text

**Decision:** Treat codes such as `001` and `0004` as strings, not integers.

**Why:** They are identifiers, not quantities. Numeric conversion would lose leading zeros.

## D005 — Use a staging table and an analytics star schema

**Decision:** Keep `staging.official_price_observations` source-oriented. Build `dim_product`, `dim_month`, and `fact_monthly_official_price` for analytics.

**Why:** Staging simplifies ingestion and reconciliation; dimensions separate descriptive attributes from measurements and allow consistent analytical joins.

## D006 — Reconcile live tables to the latest complete snapshot

**Decision:** Treat each registered, count-validated source snapshot as authoritative for the live staging and analytics tables. The loader checks that normalization produced the registered product-by-month grid, upserts included observations, and deletes omitted observations in the same transaction. Loaders are serialized, and snapshots older than the currently loaded snapshot are rejected.

**Limitations:**

- A source correction overwrites the current value; the live fact table is not a bitemporal/versioned history.
- Raw snapshots and the snapshot registry preserve evidence needed for replay, but retainment of raw files must be backed up and managed operationally.
- Grid checks catch truncated or incomplete normalization output, but cannot prove the source publisher itself returned a complete dataset; missing source fields are retained as explicit missing observations, and the source contract still needs monitoring.

**Future option:** Add versioned source observations if users need to compare what the publisher reported across snapshot dates.

## D007 — Analytical views use calendar-based joins, not positional LAG

**Original approach:** Used `LAG(..., 12)` ordered by month.
**Current decision:** Implemented in `sql/011_create_analytics_views.sql` using calendar interval arithmetic:
```sql
LEFT JOIN analytics.dim_month AS comparison_month
    ON comparison_month.month_start = (current_month.month_start - INTERVAL '1 year')::DATE
```
**Why:** Guarantees that year-over-year comparisons match the exact calendar month 12 months earlier, even if an intervening month is missing or incomplete. Positional lag could silently compare against the wrong month if timeline gaps exist.

## D008 — Relational and index design

**Decision:** Primary key on `fact_monthly_official_price (product_key, month_key)` covers lookups and foreign key constraints. Indexes on `(month_start)` and `(month_key)` enable efficient analytical views and partition window functions for rankings.

## D009 — Orchestration with Apache Airflow 3 and standalone local runner

**Decision:** Maintain two ways to run the workflow:
1. `scripts/run_pipeline.py`: Lightweight standalone runner for quick local dev / CI without container overhead.
2. Apache Airflow 3 (`pricepulse_pipeline` and `pricepulse_snapshot_replay` DAGs): Operational scheduling with bounded retries, task-level lineage, and automated test execution.

## D010 — Runtime credentials and least-privilege database roles

**Decision:** All services read credentials from `.env` via environment variables. Two distinct PostgreSQL roles enforce least privilege:
- `pricepulse_dev`: Read/write access on `staging`, `analytics`, and `audit` for pipeline ingestion and snapshot replay.
- `pricepulse_api`: Read-only access (`SELECT`) on `analytics.*` and `audit.source_snapshot`; explicitly no access to `staging` or modification capabilities.
Credentials are never committed or logged.

## D011 — Automated idempotent migration runner

**Decision:** Implemented `scripts/migrate.py` tracked in `audit.schema_migration` using SHA-256 checksums. Supports both one-time DDL and repeatable view definitions (`CREATE OR REPLACE VIEW`). Runs automatically in Docker Compose before API and Airflow containers start.

## D012 — Read-only API and server-side analytical views

**Decision:** FastAPI backend (`app/`) reads directly from PostgreSQL analytical views (`vw_monthly_price_changes`, `vw_year_over_year_price_changes`, `vw_yoy_price_change_rankings`). The API does not recompute statistics or download external data on HTTP requests. A lightweight dashboard is rendered via Jinja2 templates and vanilla JavaScript with SVG time-series charts. Missing prices are rendered as visual gaps, never fabricated.
