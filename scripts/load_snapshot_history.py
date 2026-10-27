
import os
import hashlib
import json
import math
import re
from datetime import date, datetime, timezone
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"

SOURCE_URL = (
    "https://api.siat.stat.uz/media/uploads/"
    "sdmx/sdmx_data_1308.json"
)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "pricepulse"),
    "user": os.getenv("DB_USER", "pricepulse_dev"),
}

SEMANTIC_HASH_VERSION = 2

SNAPSHOT_INSERT_SQL = """
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
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
RETURNING snapshot_id
"""


def parse_period(column: str) -> date | None:
    """Parse source month labels, including Cyrillic or Latin M."""
    if not re.match(r"^\d{4}-", column):
        return None

    parts = re.findall(r"\d+", column)

    if (
        len(parts) != 2
        or len(parts[0]) != 4
        or len(parts[1]) != 2
    ):
        raise ValueError(
            f"Unexpected monthly column: {column!r}"
        )

    year, month = map(int, parts)

    try:
        return date(year, month, 1)
    except ValueError as exc:
        raise ValueError(
            f"Invalid monthly column: {column!r}"
        ) from exc


def timestamp_from_filename(path: Path) -> datetime:
    match = re.fullmatch(
        r"official_prices_(\d{8}T\d{6}Z)",
        path.stem,
    )

    if not match:
        raise ValueError(
            f"Snapshot has an invalid timestamped filename: {path.name}"
        )

    return datetime.strptime(
        match.group(1),
        "%Y%m%dT%H%M%SZ",
    ).replace(tzinfo=timezone.utc)


def read_snapshot(path: Path) -> dict:
    raw_bytes = path.read_bytes()
    payload = json.loads(raw_bytes)

    if (
        not isinstance(payload, list)
        or len(payload) != 1
        or not isinstance(payload[0], dict)
    ):
        raise ValueError(f"Unexpected JSON structure: {path.name}")

    dataset = payload[0]
    metadata = dataset.get("metadata")
    records = dataset.get("data")

    if not isinstance(metadata, list):
        raise ValueError(f"Invalid metadata in {path.name}")

    if not isinstance(records, list) or not records:
        raise ValueError(f"Invalid product records in {path.name}")

    products = {}
    observations = {}
    period_columns = {}

    for record in records:
        if not isinstance(record, dict):
            raise TypeError("Every product record must be an object")

        code = record.get("Code")

        if not isinstance(code, str) or not code.strip():
            raise ValueError("Missing or invalid product code")

        if code in products:
            raise ValueError(f"Duplicate product code: {code}")

        products[code] = {
            "product_name_uz": record.get("Klassifikator"),
            "product_name_ru": record.get("Klassifikator_ru"),
            "product_name_en": record.get("Klassifikator_en"),
            "product_name_uz_cyrillic": record.get("Klassifikator_uzc"),
        }

        for column, value in record.items():
            period = parse_period(column)

            if period is None:
                continue

            previous_column = period_columns.get(period)

            if (
                previous_column is not None
                and previous_column != column
            ):
                raise ValueError(
                    f"Multiple source columns represent {period}: "
                    f"{previous_column!r}, {column!r}"
                )

            period_columns[period] = column
            key = (code, period)

            if key in observations:
                raise ValueError(
                    f"Duplicate product-month observation: {key}"
                )

            if value is not None:
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                ):
                    raise ValueError(
                        f"Invalid source price for {key}: {value!r}"
                    )

            observations[key] = {
                "source_period_key": column,
                "source_price": value,
            }

    if not period_columns:
        raise ValueError(f"No month columns found in {path.name}")


    # Canonical product attributes must use the same keys as
    # compare_snapshots.py so both tools calculate identical hashes.
    semantic_products = {
        code: {
            "uz": names["product_name_uz"],
            "ru": names["product_name_ru"],
            "en": names["product_name_en"],
            "uzc": names["product_name_uz_cyrillic"],
        }
        for code, names in products.items()
    }

    semantic_payload = {
        "products": semantic_products,
        "observations": [
            [
                code,
                period.strftime("%Y-%m"),
                value["source_price"],
            ]
            for (code, period), value in sorted(observations.items())
        ],
    }

    semantic_bytes = json.dumps(
        semantic_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    semantic_hash = hashlib.sha256(semantic_bytes).hexdigest()

    return {
        "filename": path.name,
        "fetched_at": timestamp_from_filename(path),
        "raw_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "semantic_sha256": semantic_hash,
        "metadata": metadata,
        "products": products,
        "observations": observations,
        "period_count": len(period_columns),
        "observation_count": len(observations),
    }


def snapshot_insert_params(snapshot: dict) -> tuple:
    """Bind values for SNAPSHOT_INSERT_SQL, including hash version."""
    return (
        snapshot["filename"],
        snapshot["fetched_at"],
        SOURCE_URL,
        snapshot["raw_sha256"],
        snapshot["semantic_sha256"],
        SEMANTIC_HASH_VERSION,
        len(snapshot["products"]),
        snapshot["period_count"],
        snapshot["observation_count"],
        Jsonb(snapshot["metadata"]),
    )


def register_snapshots() -> dict:
    files = sorted(RAW_DIR.glob("official_prices_*.json"))

    if not files:
        raise FileNotFoundError(
            f"No raw snapshots found in {RAW_DIR}"
        )

    registered = 0
    skipped = 0
    product_rows = 0
    observation_rows = 0

    password = os.getenv("DB_PASSWORD")

    if not password:
        raise RuntimeError(
            "DB_PASSWORD must be set for snapshot registration"
        )

    with psycopg.connect(
        **DB_CONFIG,
        password=password,
    ) as conn:
        with conn.cursor() as cur:
            hashes_upgraded = 0
            for path in files:
                snapshot = read_snapshot(path)

                cur.execute(
                    """
                    SELECT
                        snapshot_id,
                        raw_sha256,
                        semantic_sha256,
                        semantic_hash_version
                    FROM audit.source_snapshot
                    WHERE snapshot_filename = %s
                    """,
                    (snapshot["filename"],),
                )


                existing = cur.fetchone()

                if existing:
                    (
                        snapshot_id,
                        old_raw_hash,
                        old_semantic_hash,
                        old_hash_version,
                    ) = existing

                    # A filename must continue to identify the same
                    # original downloaded bytes.
                    if old_raw_hash != snapshot["raw_sha256"]:
                        raise ValueError(
                            "Raw content changed for an existing "
                            f"snapshot: {snapshot['filename']}"
                        )

                    if old_hash_version > SEMANTIC_HASH_VERSION:
                        raise ValueError(
                            "Database semantic-hash version is newer "
                            "than this loader."
                        )

                    if old_hash_version < SEMANTIC_HASH_VERSION:
                        # Upgrade derived metadata, not the source data.
                        cur.execute(
                            """
                            UPDATE audit.source_snapshot
                            SET semantic_sha256 = %s,
                                semantic_hash_version = %s
                            WHERE snapshot_id = %s
                            """,
                            (
                                snapshot["semantic_sha256"],
                                SEMANTIC_HASH_VERSION,
                                snapshot_id,
                            ),
                        )

                        hashes_upgraded += 1

                    elif old_semantic_hash != snapshot["semantic_sha256"]:
                        raise ValueError(
                            "Semantic hash mismatch for "
                            f"{snapshot['filename']}"
                        )

                    skipped += 1
                    continue


                cur.execute(
                    SNAPSHOT_INSERT_SQL,
                    snapshot_insert_params(snapshot),
                )

                snapshot_id = cur.fetchone()[0]

                cur.executemany(
                    """
                    INSERT INTO audit.source_snapshot_product (
                        snapshot_id,
                        product_code,
                        product_name_uz,
                        product_name_ru,
                        product_name_en,
                        product_name_uz_cyrillic
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    [
                        (
                            snapshot_id,
                            code,
                            names["product_name_uz"],
                            names["product_name_ru"],
                            names["product_name_en"],
                            names["product_name_uz_cyrillic"],
                        )
                        for code, names in snapshot["products"].items()
                    ],
                )

                cur.executemany(
                    """
                    INSERT INTO audit.source_snapshot_price_observation (
                        snapshot_id,
                        product_code,
                        period,
                        source_period_key,
                        source_price_uzs_per_kg
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    [
                        (
                            snapshot_id,
                            code,
                            period,
                            value["source_period_key"],
                            value["source_price"],
                        )
                        for (code, period), value
                        in snapshot["observations"].items()
                    ],
                )

                registered += 1
                product_rows += len(snapshot["products"])
                observation_rows += snapshot["observation_count"]

    return {
        "files_found": len(files),
        "registered": registered,
        "skipped": skipped,
        "product_rows": product_rows,
        "observation_rows": observation_rows,
        "hashes_upgraded": hashes_upgraded,
    }


def main() -> None:
    results = register_snapshots()

    print("=== SNAPSHOT HISTORY LOAD ===")
    print(f"Files found: {results['files_found']}")
    print(f"New snapshots registered: {results['registered']}")
    print(f"Existing snapshots skipped: {results['skipped']}")
    print("Existing snapshot hashes upgraded: "f"{results['hashes_upgraded']}")
    print(f"Product rows inserted: {results['product_rows']:,}")
    print("Observation rows inserted: "f"{results['observation_rows']:,}")


if __name__ == "__main__":
    main()
