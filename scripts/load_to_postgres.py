
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
    "host": "localhost",
    "port": 5432,
    "dbname": "pricepulse",
    "user": "pricepulse_dev",
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

    password = getpass(
        f"Password for PostgreSQL user "
        f"{DB_CONFIG['user']}: "
    )

    # The connection context commits on success and rolls back
    # if an exception escapes the block.
    with psycopg.connect(
        **DB_CONFIG,
        password=password,
    ) as conn:
        with conn.cursor() as cur:
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
                "products_affected": products_affected,
                "months_inserted": months_inserted,
                "facts_affected": facts_affected,
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
    print(f"Product dimension rows affected: {results['products_affected']:,}")
    print(f"New month rows inserted: {results['months_inserted']:,}")
    print(f"Fact rows affected: {results['facts_affected']:,}")

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
