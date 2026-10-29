from __future__ import annotations

import csv
import hashlib
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest

from scripts import load_to_postgres


pytestmark = pytest.mark.integration


def _database_settings() -> dict:
    test_database_name = os.environ["PRICEPULSE_TEST_DB_NAME"]
    if "test" not in test_database_name.lower():
        raise ValueError(
            "PRICEPULSE_TEST_DB_NAME must clearly identify a disposable "
            "test database"
        )
    if test_database_name == os.getenv("DB_NAME", "pricepulse"):
        raise ValueError(
            "PRICEPULSE_TEST_DB_NAME must not be the configured application "
            "database"
        )

    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "dbname": test_database_name,
        "user": os.getenv("DB_USER", "pricepulse_dev"),
        "password": os.environ["DB_PASSWORD"],
    }


def _admin_settings(database_settings: dict) -> dict:
    return {
        **database_settings,
        "user": os.getenv("POSTGRES_USER", "postgres"),
        "password": os.environ["POSTGRES_ADMIN_PASSWORD"],
    }


def _register_snapshot(connection, filename: str, fetched_at: str, rows) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO audit.source_snapshot (
                snapshot_filename,
                fetched_at_utc,
                source_url,
                raw_sha256,
                semantic_sha256,
                semantic_hash_version,
                product_count,
                period_count,
                observation_count,
                source_metadata
            )
            VALUES (%s, %s, %s, %s, %s, 2, %s, %s, %s, '[]'::jsonb)
            """,
            (
                filename,
                fetched_at,
                "https://example.invalid/fixture",
                hashlib.sha256(filename.encode()).hexdigest(),
                hashlib.sha256((filename + "-semantic").encode()).hexdigest(),
                len({row[0] for row in rows}),
                len({row[1] for row in rows}),
                len(rows),
            ),
        )


def _write_snapshot_csv(
    path: Path,
    filename: str,
    fetched_at: str,
    rows,
) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "product_code",
                "product_name_uz",
                "product_name_ru",
                "product_name_en",
                "product_name_uz_cyrillic",
                "period",
                "source_price_uzs_per_kg",
                "source_fetched_at_utc",
                "source_snapshot",
                "average_price_uzs_per_kg",
                "price_status",
            ]
        )
        for product_code, period, price in rows:
            writer.writerow(
                [
                    product_code,
                    "",
                    "",
                    f"Product {product_code}",
                    "",
                    period,
                    price,
                    fetched_at,
                    filename,
                    price,
                    "observed",
                ]
            )


@pytest.mark.skipif(
    not os.getenv("PRICEPULSE_TEST_DB_NAME"),
    reason="Set PRICEPULSE_TEST_DB_NAME to a dedicated disposable database",
)
def test_latest_snapshot_replaces_current_rows_and_rejects_older_snapshot(
    monkeypatch,
    tmp_path,
):
    settings = _database_settings()
    monkeypatch.setitem(load_to_postgres.DB_CONFIG, "host", settings["host"])
    monkeypatch.setitem(load_to_postgres.DB_CONFIG, "port", settings["port"])
    monkeypatch.setitem(load_to_postgres.DB_CONFIG, "dbname", settings["dbname"])
    monkeypatch.setitem(load_to_postgres.DB_CONFIG, "user", settings["user"])
    monkeypatch.setenv("DB_PASSWORD", settings["password"])
    monkeypatch.setattr(
        load_to_postgres,
        "INPUT_FILE",
        tmp_path / "official_prices_analytics.csv",
    )

    snapshots = [
        (
            "official_prices_20261029T000001Z.json",
            "2026-10-29T00:00:01Z",
            [
                ("001", "2026-01-01", "10.00"),
                ("001", "2026-02-01", "11.00"),
                ("0050", "2026-01-01", "20.00"),
                ("0050", "2026-02-01", "21.00"),
            ],
        ),
        (
            "official_prices_20261029T000002Z.json",
            "2026-10-29T00:00:02Z",
            [
                ("001", "2026-01-01", "13.00"),
                ("001", "2026-03-01", "14.00"),
            ],
        ),
        (
            "official_prices_20261028T000001Z.json",
            "2026-10-28T00:00:01Z",
            [
                ("001", "2026-01-01", "9.00"),
                ("001", "2026-02-01", "10.00"),
            ],
        ),
    ]

    with psycopg.connect(**_admin_settings(settings)) as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                TRUNCATE TABLE
                    staging.official_price_observations,
                    analytics.fact_monthly_official_price,
                    analytics.dim_product,
                    analytics.dim_month,
                    audit.source_snapshot
                RESTART IDENTITY CASCADE
            """)
        for filename, fetched_at, rows in snapshots:
            _register_snapshot(connection, filename, fetched_at, rows)

    for index, (filename, fetched_at, rows) in enumerate(snapshots):
        _write_snapshot_csv(
            load_to_postgres.INPUT_FILE,
            filename,
            fetched_at,
            rows,
        )

        if index == 2:
            with pytest.raises(ValueError, match="older source snapshot"):
                load_to_postgres.load_data()
            break

        result = load_to_postgres.load_data()
        if index == 0:
            assert (
                result["staging_rows"],
                result["product_rows"],
                result["month_rows"],
                result["fact_rows"],
            ) == (4, 2, 2, 4)
        else:
            assert (
                result["staging_rows"],
                result["product_rows"],
                result["month_rows"],
                result["fact_rows"],
            ) == (2, 1, 2, 2)
            assert result["staging_deleted"] == 3
            assert result["facts_deleted"] == 3
            assert result["products_deleted"] == 1
            assert result["months_deleted"] == 1

    with psycopg.connect(**_admin_settings(settings)) as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT product.product_code, month.month_start,
                       fact.source_price_uzs_per_kg
                FROM analytics.fact_monthly_official_price AS fact
                JOIN analytics.dim_product AS product USING (product_key)
                JOIN analytics.dim_month AS month USING (month_key)
                ORDER BY month.month_start
            """)
            assert cursor.fetchall() == [
                ("001", date(2026, 1, 1), Decimal("13.00")),
                ("001", date(2026, 3, 1), Decimal("14.00")),
            ]
