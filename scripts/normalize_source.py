import argparse
import csv
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"

OUTPUT_FILE = OUTPUT_DIR / "official_prices_long.csv"


def find_latest_snapshot() -> Path:
    """Find the newest timestamped raw snapshot."""
    files = list(RAW_DIR.glob("official_prices_*.json"))

    if not files:
        raise FileNotFoundError(
            f"No raw JSON snapshots found in {RAW_DIR}"
        )

    # The filenames contain sortable UTC timestamps.
    return max(files, key=lambda path: path.name)


def parse_period(column_name: str) -> date | None:
    """
    Convert a source column such as 2021-М01 or 2022-M01
    into a date representing the first day of that month.

    Return None for columns that are not monthly periods.
    """
    if not re.match(r"^\d{4}-", column_name):
        return None

    # Extract digits, ignoring whether the separator
    # contains a Latin or Cyrillic character.
    parts = re.findall(r"\d+", column_name)

    if (
        len(parts) != 2
        or len(parts[0]) != 4
        or len(parts[1]) != 2
    ):
        raise ValueError(
            f"Unexpected monthly column format: {column_name!r}"
        )

    year = int(parts[0])
    month = int(parts[1])

    try:
        return date(year, month, 1)
    except ValueError as exc:
        raise ValueError(
            f"Invalid year/month in column: {column_name!r}"
        ) from exc


def main(
    source_path: Path | None = None,
    output_path: Path | None = None,
) -> None:
    raw_file = (
        source_path.resolve()
        if source_path is not None
        else find_latest_snapshot()
    )


    output_file = (output_path or OUTPUT_FILE).resolve()

    try:
        output_file.relative_to(OUTPUT_DIR.resolve())
    except ValueError as exc:
        raise ValueError(
            "Output path must be inside data/processed/"
        ) from exc


    if not raw_file.is_file():
        raise FileNotFoundError(
            f"Source snapshot not found: {raw_file}"
        )

    if raw_file.parent != RAW_DIR.resolve():
        raise ValueError(
            "The source snapshot must be inside data/raw/"
        )

    # Recover the fetch timestamp from the snapshot filename.
    match = re.search(
        r"_(\d{8}T\d{6}Z)$",
        raw_file.stem,
    )

    if not match:
        raise ValueError(
            f"Snapshot filename has no valid timestamp: {raw_file.name}"
        )

    fetched_at = (
        datetime.strptime(
            match.group(1), "%Y%m%dT%H%M%SZ"
        )
        .replace(tzinfo=timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )

    # Load the previously downloaded raw JSON.
    with raw_file.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    if (
        not isinstance(payload, list)
        or len(payload) != 1
        or not isinstance(payload[0], dict)
    ):
        raise ValueError("Unexpected top-level dataset structure")

    records = payload[0].get("data")

    if not isinstance(records, list) or not records:
        raise ValueError("Dataset contains no valid data records")

    # Validate product records and preserve their identifiers.
    seen_codes = set()

    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise TypeError(f"Record {index} is not an object")

        code = record.get("Code")

        if not isinstance(code, str) or not code.strip():
            raise ValueError(
                f"Record {index} has a missing or invalid product code"
            )

        if code in seen_codes:
            raise ValueError(f"Duplicate product code: {code!r}")

        seen_codes.add(code)

    # Discover all monthly columns across the source records.
    periods = {}

    for record in records:
        for column_name in record:
            period = parse_period(column_name)

            if period is not None:
                periods[column_name] = period

    if not periods:
        raise ValueError("No monthly price columns were found")

    # Sort chronologically, not alphabetically.
    period_columns = sorted(
        periods,
        key=lambda column: periods[column],
    )

    period_dates = [periods[column] for column in period_columns]

    if len(set(period_dates)) != len(period_dates):
        raise ValueError(
            "Multiple source columns represent the same month"
        )

    output_file.parent.mkdir(parents=True, exist_ok=True)

    temporary_file = output_file.with_name(
        f".{output_file.name}.tmp"
    )

    row_count = 0
    missing_period_fields = 0
    missing_price_values = 0

    fieldnames = [
        "product_code",
        "product_name_uz",
        "product_name_ru",
        "product_name_en",
        "product_name_uz_cyrillic",
        "period",
        "average_price_uzs_per_kg",
        "source_fetched_at_utc",
        "source_snapshot",
    ]

    try:
        with temporary_file.open(
            "w", encoding="utf-8", newline=""
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=fieldnames,
            )
            writer.writeheader()

            for record in records:
                for column_name in period_columns:
                    if column_name not in record:
                        missing_period_fields += 1
                        price = ""
                    else:
                        raw_price = record[column_name]

                        if raw_price is None or raw_price == "":
                            missing_price_values += 1
                            price = ""
                        elif (
                            isinstance(raw_price, bool)
                            or not isinstance(raw_price, (int, float))
                        ):
                            raise TypeError(
                                f"Invalid price for product "
                                f"{record['Code']!r}, "
                                f"period {column_name!r}: "
                                f"{raw_price!r}"
                            )
                        elif raw_price < 0:
                            raise ValueError(
                                f"Negative price for product "
                                f"{record['Code']!r}, "
                                f"period {column_name!r}"
                            )
                        else:
                            price = raw_price

                    writer.writerow(
                        {
                            "product_code": record["Code"],
                            "product_name_uz": (
                                record.get("Klassifikator") or ""
                            ),
                            "product_name_ru": (
                                record.get("Klassifikator_ru") or ""
                            ),
                            "product_name_en": (
                                record.get("Klassifikator_en") or ""
                            ),
                            "product_name_uz_cyrillic": (
                                record.get("Klassifikator_uzc") or ""
                            ),
                            "period": periods[column_name].isoformat(),
                            "average_price_uzs_per_kg": price,
                            "source_fetched_at_utc": fetched_at,
                            "source_snapshot": raw_file.name,
                        }
                    )

                    row_count += 1

        # Replace the previous output only after a successful write.
        temporary_file.replace(output_file)

    except Exception:
        temporary_file.unlink(missing_ok=True)
        raise

    print("\n=== TRANSFORMATION SUMMARY ===")
    print(f"Source file: {raw_file.name}")
    print(f"Products: {len(records)}")
    print(f"Monthly periods: {len(period_columns)}")
    print(
        f"Period range: {period_dates[0].isoformat()} "
        f"to {period_dates[-1].isoformat()}"
    )
    print(f"Rows written: {row_count:,}")
    print(f"Missing period fields: {missing_period_fields:,}")
    print(f"Missing price values: {missing_price_values:,}")
    print(f"Output file: {output_file.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Normalize an official price snapshot"
    )

    parser.add_argument(
        "--source",
        type=Path,
        help="Exact raw JSON snapshot to process",
    )

    parser.add_argument(
        "--output",
        type=Path,
        help="Output CSV path inside data/processed/",
    )

    args = parser.parse_args()
    main(args.source, args.output)
