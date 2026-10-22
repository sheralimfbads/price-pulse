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

## D006 — Upsert current product-month values

**Decision:** Use primary keys and `ON CONFLICT` upserts to make the local loader repeatable without creating duplicate product-month facts.

**Limitations:**

- Upserts can rewrite rows even when values have not changed.
- When the source revises an old price, the prior value is overwritten in the current fact table.
- If a product-month row disappears from a future source snapshot, this loader does not automatically delete the old row.
- Raw snapshots preserve some evidence of prior versions on the local machine, but the database does not yet model source revisions.

**Future option:** Add load-batch and source-observation history tables or a snapshot-diff process if revision history becomes a requirement.

## D007 — Current year-over-year SQL uses `LAG(..., 12)`

**Decision:** Compare with twelve preceding rows per product.

**Assumption:** Each product has a complete, correctly ordered row for every month. The inspected dataset has 69 rows for each of 41 products.

**Limitation:** If missing months become possible, twelve preceding rows may not be the same calendar month last year. Match on an explicit date or join to `period - INTERVAL '1 year'` instead.

## D008 — No additional period index yet

**Evidence:** The product-history query used the primary-key index and ran quickly; filtering all products by period used a sequential scan and ran in under a millisecond in one local experiment.

**Decision:** Keep the schema simple for the current 2,829-row table.

**Why:** Indexes take space and increase write costs. Revisit when representative queries or a larger dataset demonstrate a real benefit. Local timings are not a benchmark.

## D009 — Local Python runner before Airflow

**Decision:** Coordinate the scripts with a small sequential runner and stop on the first non-zero exit code.

**Why:** The workflow's stages, dependencies, and failure behavior can be understood before adding a scheduler.

**Limitation:** No scheduling, task retries, monitoring UI, alerting, or native backfills yet.

## D010 — Credentials are supplied at runtime

**Decision:** The current loader uses `getpass` for the local PostgreSQL password.

**Why:** The password should not be embedded in code or committed.

**Next step:** For non-interactive automation, use a documented secret mechanism such as environment variables injected at runtime or an Airflow connection/secret backend. Never commit the actual secret.
