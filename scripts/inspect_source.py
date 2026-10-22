
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"


def find_latest_snapshot() -> Path:
    snapshots = sorted(
        RAW_DIR.glob("official_prices_*.json"),
        key=lambda path: path.name,
    )

    if not snapshots:
        raise FileNotFoundError(
            f"No source snapshots found in {RAW_DIR}"
        )

    return snapshots[-1]


def main() -> None:
    raw_file = find_latest_snapshot()

    with raw_file.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    if (
        not isinstance(payload, list)
        or len(payload) != 1
        or not isinstance(payload[0], dict)
    ):
        raise ValueError("Unexpected source JSON structure")

    dataset = payload[0]
    metadata = dataset.get("metadata")
    records = dataset.get("data")

    if not isinstance(metadata, list):
        raise ValueError("Invalid metadata")

    if not isinstance(records, list):
        raise ValueError("Invalid data records")

    print(f"Snapshot: {raw_file.name}")
    print(f"Metadata items: {len(metadata)}")
    print(f"Product records: {len(records)}")

    print("\n=== METADATA ===")

    for item in metadata:
        if isinstance(item, dict):
            name = item.get("name_en") or item.get("name_uz", "?")
            value = item.get("value_en") or item.get("value_uz", "?")
            print(f"{name}: {value}")

    print("\n=== PRODUCT SAMPLE ===")

    for record in records[:3]:
        if not isinstance(record, dict):
            continue

        month_columns = [
            key for key in record
            if re.match(r"^\d{4}-", key)
        ]

        print(
            f"Code={record.get('Code')} | "
            f"Product={record.get('Klassifikator_en')} | "
            f"Monthly columns={len(month_columns)}"
        )


if __name__ == "__main__":
    main()
