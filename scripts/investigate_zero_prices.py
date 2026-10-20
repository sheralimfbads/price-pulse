
import csv
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROCESSED_FILE = ROOT / "data" / "processed" / "official_prices_long.csv"
RAW_DIR = ROOT / "data" / "raw"


def period_from_column(column: str) -> str | None:
    """Convert a source month column into YYYY-MM-01."""
    parts = re.findall(r"\d+", column)

    if (
        len(parts) != 2
        or len(parts[0]) != 4
        or len(parts[1]) != 2
    ):
        return None

    year, month = map(int, parts)

    if not 1 <= month <= 12:
        return None

    return f"{year:04d}-{month:02d}-01"


def main() -> None:
    with PROCESSED_FILE.open(
        "r", encoding="utf-8", newline=""
    ) as file:
        rows = list(csv.DictReader(file))

    zero_rows = [
        row
        for row in rows
        if row["average_price_uzs_per_kg"]
        and float(row["average_price_uzs_per_kg"]) == 0
    ]

    if not zero_rows:
        print("No zero-price observations found.")
        return

    print(f"Zero-price observations found: {len(zero_rows)}")

    # Group observations by their original source snapshot.
    by_snapshot = {}

    for row in zero_rows:
        snapshot = row["source_snapshot"]
        by_snapshot.setdefault(snapshot, []).append(row)

    for snapshot, observations in by_snapshot.items():
        raw_file = RAW_DIR / snapshot

        if not raw_file.exists():
            raise FileNotFoundError(
                f"Original snapshot not found: {raw_file}"
            )

        with raw_file.open("r", encoding="utf-8") as file:
            payload = json.load(file)

        source_records = payload[0]["data"]

        records_by_code = {
            record["Code"]: record
            for record in source_records
        }

        print(f"\n=== SOURCE SNAPSHOT: {snapshot} ===")

        for row in observations:
            code = row["product_code"]
            period = row["period"]

            record = records_by_code.get(code)

            if record is None:
                print(f"ERROR: Product {code} not found")
                continue

            matching_columns = [
                (column, value)
                for column, value in record.items()
                if period_from_column(column) == period
            ]

            print(
                f"\n{code} | {row['product_name_en']} "
                f"| {period}"
            )
            print(
                "Processed CSV value:",
                row["average_price_uzs_per_kg"],
            )

            if len(matching_columns) != 1:
                print(
                    "ERROR: Expected exactly one source month "
                    f"column, found {len(matching_columns)}"
                )
                continue

            source_column, source_value = matching_columns[0]

            print(f"Original JSON field: {source_column!r}")
            print(f"Original JSON value: {source_value!r}")

            try:
                matches = (
                    source_value is not None
                    and not isinstance(source_value, bool)
                    and float(source_value) == 0
                )
            except (TypeError, ValueError):
                matches = False

            if matches:
                print("RESULT: Zero is present in the raw source.")
            else:
                print("RESULT: Investigate the source/CSV mismatch.")


if __name__ == "__main__":
    main()
