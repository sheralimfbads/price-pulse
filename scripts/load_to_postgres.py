
import os
import sys

from getpass import getpass
from pathlib import Path

import psycopg


ROOT = Path(__file__).resolve().parents[1]

INPUT_FILE = (
    ROOT
    / "data"
    / "processed"
    / "official_prices_analytics.csv"
)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "pricepulse"),
    "user": os.getenv("DB_USER", "pricepulse_dev"),
}

COLUMNS = """
    product_code,
    product_name_uz,
    product_name_ru,
    product_name_en,
    product_name_uz_cyrillic,
    period,
    source_price_uzs_per_kg,
    source_fetched_at_utc,
    source_snapshot,
    average_price_uzs_per_kg,
    price_status
"""

STAGE_UPSERT_SQL = """
INSERT INTO staging.official_price_observations (
    product_code,
    product_name_uz,
    product_name_ru,
    product_name_en,
    product_name_uz_cyrillic,
    period,
    source_price_uzs_per_kg,
    source_fetched_at_utc,
    source_snapshot,
    average_price_uzs_per_kg,
    price_status
)
SELECT
    product_code,
    product_name_uz,
    product_name_ru,
    product_name_en,
    product_name_uz_cyrillic,
    period,
    source_price_uzs_per_kg,
    source_fetched_at_utc,
    source_snapshot,
    average_price_uzs_per_kg,
    price_status
FROM pricepulse_import
ON CONFLICT (product_code, period)
DO UPDATE SET
    product_name_uz = EXCLUDED.product_name_uz,
    product_name_ru = EXCLUDED.product_name_ru,
    product_name_en = EXCLUDED.product_name_en,
    product_name_uz_cyrillic = EXCLUDED.product_name_uz_cyrillic,
    source_price_uzs_per_kg = EXCLUDED.source_price_uzs_per_kg,
    source_fetched_at_utc = EXCLUDED.source_fetched_at_utc,
    source_snapshot = EXCLUDED.source_snapshot,
    average_price_uzs_per_kg = EXCLUDED.average_price_uzs_per_kg,
    price_status = EXCLUDED.price_status
"""

STAGE_DELETE_MISSING_SQL = """
DELETE FROM staging.official_price_observations AS old_observation
WHERE NOT EXISTS (
    SELECT 1
    FROM pricepulse_import AS incoming
    WHERE incoming.product_code = old_observation.product_code
      AND incoming.period = old_observation.period
)
"""

FACT_DELETE_MISSING_SQL = """
DELETE FROM analytics.fact_monthly_official_price AS fact_row
USING analytics.dim_product AS product_dim,
      analytics.dim_month AS month_dim
WHERE fact_row.product_key = product_dim.product_key
  AND fact_row.month_key = month_dim.month_key
  AND NOT EXISTS (
      SELECT 1
      FROM staging.official_price_observations AS observation
      WHERE observation.product_code = product_dim.product_code
        AND observation.period = month_dim.month_start
  )
"""

PRODUCT_DELETE_ORPHANS_SQL = """
DELETE FROM analytics.dim_product AS product_dim
WHERE NOT EXISTS (
    SELECT 1
    FROM staging.official_price_observations AS observation
    WHERE observation.product_code = product_dim.product_code
)
"""

MONTH_DELETE_ORPHANS_SQL = """
DELETE FROM analytics.dim_month AS month_dim
WHERE NOT EXISTS (
    SELECT 1
    FROM staging.official_price_observations AS observation
    WHERE observation.period = month_dim.month_start
)
"""

PRODUCT_UPSERT_SQL = """
INSERT INTO analytics.dim_product (
    product_code,
    product_name_uz,
    product_name_ru,
    product_name_en,
    product_name_uz_cyrillic
)
SELECT DISTINCT
    product_code,
    product_name_uz,
    product_name_ru,
    product_name_en,
    product_name_uz_cyrillic
FROM staging.official_price_observations
ON CONFLICT (product_code)
DO UPDATE SET
    product_name_uz = EXCLUDED.product_name_uz,
    product_name_ru = EXCLUDED.product_name_ru,
    product_name_en = EXCLUDED.product_name_en,
    product_name_uz_cyrillic = EXCLUDED.product_name_uz_cyrillic
"""

MONTH_UPSERT_SQL = """
INSERT INTO analytics.dim_month (
    month_key,
    month_start,
    calendar_year,
    quarter_number,
    month_number
)
SELECT DISTINCT
    EXTRACT(YEAR FROM period)::INTEGER * 100
        + EXTRACT(MONTH FROM period)::INTEGER,
    period,
    EXTRACT(YEAR FROM period)::SMALLINT,
    EXTRACT(QUARTER FROM period)::SMALLINT,
    EXTRACT(MONTH FROM period)::SMALLINT
FROM staging.official_price_observations
ON CONFLICT (month_key)
DO NOTHING
"""

FACT_UPSERT_SQL = """
INSERT INTO analytics.fact_monthly_official_price (
    product_key,
    month_key,
    source_price_uzs_per_kg,
    average_price_uzs_per_kg,
    price_status,
    source_fetched_at_utc,
    source_snapshot
)
SELECT
    p.product_key,
    m.month_key,
    s.source_price_uzs_per_kg,
    s.average_price_uzs_per_kg,
    s.price_status,
    s.source_fetched_at_utc,
    s.source_snapshot
FROM staging.official_price_observations AS s
JOIN analytics.dim_product AS p
    ON p.product_code = s.product_code
JOIN analytics.dim_month AS m
    ON m.month_start = s.period
ON CONFLICT (product_key, month_key)
DO UPDATE SET
    source_price_uzs_per_kg = EXCLUDED.source_price_uzs_per_kg,
    average_price_uzs_per_kg = EXCLUDED.average_price_uzs_per_kg,
    price_status = EXCLUDED.price_status,
    source_fetched_at_utc = EXCLUDED.source_fetched_at_utc,
    source_snapshot = EXCLUDED.source_snapshot
"""


def load_data() -> dict:
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Input CSV not found: {INPUT_FILE}"
        )

    password = os.getenv("DB_PASSWORD")

    if not password:
        if not sys.stdin.isatty():
            raise RuntimeError(
                "DB_PASSWORD must be set for non-interactive execution."
            )

        password = getpass(
            f"Password for PostgreSQL user {DB_CONFIG['user']}: "
        )

    # The connection context commits on success and rolls back
    # if an exception escapes the block.
    with psycopg.connect(
        **DB_CONFIG,
        password=password,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_advisory_xact_lock("
                "hashtextextended('pricepulse.snapshot_loader', 0))"
            )

            # Temporary table: same columns and types as staging,
            # but without its indexes and primary-key constraint.
            cur.execute("""
                CREATE TEMP TABLE pricepulse_import
                (LIKE staging.official_price_observations)
                ON COMMIT DROP
            """)

            copy_sql = f"""
                COPY pricepulse_import ({COLUMNS})
                FROM STDIN
                WITH (FORMAT CSV, HEADER TRUE, NULL '')
            """

            # Stream the file in chunks instead of loading the
            # entire CSV into Python memory.
            with cur.copy(copy_sql) as copy:
                with INPUT_FILE.open("rb") as source:
                    while chunk := source.read(1024 * 1024):
                        copy.write(chunk)

            cur.execute(
                "SELECT COUNT(*) FROM pricepulse_import"
            )
            input_rows = cur.fetchone()[0]

            if input_rows == 0:
                raise ValueError("Input CSV contains no data rows")

            cur.execute("""
                SELECT
                    COUNT(DISTINCT source_snapshot),
                    COUNT(DISTINCT source_fetched_at_utc),
                    MAX(source_fetched_at_utc),
                    MAX(source_snapshot)
                FROM pricepulse_import
            """)
            snapshot_count, fetched_at_count, fetched_at, snapshot_name = (
                cur.fetchone()
            )
            if snapshot_count != 1 or fetched_at_count != 1:
                raise ValueError(
                    "Input must contain exactly one source snapshot "
                    "and fetch timestamp"
                )

            cur.execute("""
                SELECT product_count, period_count, observation_count
                FROM audit.source_snapshot
                WHERE snapshot_filename = %s
            """, (snapshot_name,))
            registered_counts = cur.fetchone()
            if registered_counts is None:
                raise ValueError(
                    f"Source snapshot is not registered: {snapshot_name}"
                )

            cur.execute("""
                SELECT
                    COUNT(DISTINCT product_code),
                    COUNT(DISTINCT period)
                FROM pricepulse_import
            """)
            imported_product_count, imported_period_count = cur.fetchone()
            expected_rows = registered_counts[0] * registered_counts[1]
            if (
                input_rows != expected_rows
                or imported_product_count != registered_counts[0]
                or imported_period_count != registered_counts[1]
                or registered_counts[2] > expected_rows
            ):
                raise ValueError(
                    "Imported product-month grid does not match the "
                    f"registered snapshot dimensions: {snapshot_name}"
                )

            cur.execute("""
                SELECT source_fetched_at_utc, source_snapshot
                FROM staging.official_price_observations
                ORDER BY source_fetched_at_utc DESC, source_snapshot DESC
                LIMIT 1
            """)
            current_snapshot = cur.fetchone()
            if current_snapshot and current_snapshot > (
                fetched_at,
                snapshot_name,
            ):
                raise ValueError(
                    "Refusing to replace current analytics with an older "
                    "source snapshot"
                )

            # Check the key before the staging upsert.
            cur.execute("""
                SELECT product_code, period, COUNT(*)
                FROM pricepulse_import
                GROUP BY product_code, period
                HAVING COUNT(*) > 1
                LIMIT 1
            """)

            duplicate = cur.fetchone()

            if duplicate is not None:
                raise ValueError(
                    "Duplicate product-month key in input: "
                    f"{duplicate}"
                )

            # 1. Upsert normalized observations into staging.
            cur.execute(STAGE_UPSERT_SQL)
            staging_affected = cur.rowcount

            # Reconcile the snapshot's complete current-state contents.
            cur.execute(STAGE_DELETE_MISSING_SQL)
            staging_deleted = cur.rowcount

            cur.execute(FACT_DELETE_MISSING_SQL)
            facts_deleted = cur.rowcount

            cur.execute(PRODUCT_DELETE_ORPHANS_SQL)
            products_deleted = cur.rowcount

            cur.execute(MONTH_DELETE_ORPHANS_SQL)
            months_deleted = cur.rowcount

            # 2. Update dimensions.
            cur.execute(PRODUCT_UPSERT_SQL)
            products_affected = cur.rowcount

            cur.execute(MONTH_UPSERT_SQL)
            months_inserted = cur.rowcount

            # 3. Upsert facts using dimension keys.
            cur.execute(FACT_UPSERT_SQL)
            facts_affected = cur.rowcount

            # 4. Verify the final database state.
            cur.execute("""
                SELECT
                    (SELECT COUNT(*)
                     FROM staging.official_price_observations),
                    (SELECT COUNT(*)
                     FROM analytics.dim_product),
                    (SELECT COUNT(*)
                     FROM analytics.dim_month),
                    (SELECT COUNT(*)
                     FROM analytics.fact_monthly_official_price)
            """)

            (
                staging_rows,
                product_rows,
                month_rows,
                fact_rows,
            ) = cur.fetchone()

            if (
                staging_rows,
                product_rows,
                month_rows,
                fact_rows,
            ) != (
                input_rows,
                imported_product_count,
                imported_period_count,
                input_rows,
            ):
                raise RuntimeError(
                    "Loaded database counts do not match the validated "
                    "source snapshot; transaction will be rolled back"
                )

            cur.execute("""
                SELECT price_status, COUNT(*)
                FROM analytics.fact_monthly_official_price
                GROUP BY price_status
                ORDER BY price_status
            """)

            status_counts = dict(cur.fetchall())

            results = {
                "input_rows": input_rows,
                "staging_affected": staging_affected,
                "staging_deleted": staging_deleted,
                "products_affected": products_affected,
                "products_deleted": products_deleted,
                "months_inserted": months_inserted,
                "months_deleted": months_deleted,
                "facts_affected": facts_affected,
                "facts_deleted": facts_deleted,
                "staging_rows": staging_rows,
                "product_rows": product_rows,
                "month_rows": month_rows,
                "fact_rows": fact_rows,
                "status_counts": status_counts,
            }

    # The transaction has committed successfully by this point.
    return results


def main() -> None:
    results = load_data()

    print("\n=== PRICEPULSE LOAD SUMMARY ===")
    print(f"CSV input rows: {results['input_rows']:,}")
    print(f"Staging rows affected: {results['staging_affected']:,}")
    print(f"Stale staging rows removed: {results['staging_deleted']:,}")
    print(f"Product dimension rows affected: {results['products_affected']:,}")
    print(f"Orphan product rows removed: {results['products_deleted']:,}")
    print(f"New month rows inserted: {results['months_inserted']:,}")
    print(f"Orphan month rows removed: {results['months_deleted']:,}")
    print(f"Fact rows affected: {results['facts_affected']:,}")
    print(f"Stale fact rows removed: {results['facts_deleted']:,}")

    print("\n=== FINAL ROW COUNTS ===")
    print(f"Staging: {results['staging_rows']:,}")
    print(f"Products: {results['product_rows']:,}")
    print(f"Months: {results['month_rows']:,}")
    print(f"Facts: {results['fact_rows']:,}")

    print("\n=== FACT PRICE STATUSES ===")
    for status, count in results["status_counts"].items():
        print(f"{status}: {count:,}")

    print("\nLoad transaction committed successfully.")


if __name__ == "__main__":
    main()
