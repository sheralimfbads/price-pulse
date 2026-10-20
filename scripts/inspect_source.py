
import json
from datetime import datetime, timezone
from pathlib import Path

import requests


SOURCE_URL = (
    "https://api.siat.stat.uz/media/uploads/"
    "sdmx/sdmx_data_1308.json"
)

RAW_DIR = Path("data/raw")


def main() -> None:
    # 1. Extract: request the source data.
    response = requests.get(
        SOURCE_URL,
        headers={
            "User-Agent": "PricePulse/0.1 (educational data project)"
        },
        timeout=30,
    )

    # Raise an exception for HTTP errors such as 404 or 500.
    response.raise_for_status()

    # 2. Check that the response contains valid JSON.
    payload = response.json()

    # 3. Save a timestamped snapshot of the original response.
    fetched_at = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    output_path = RAW_DIR / f"official_prices_{fetched_at}.json"
    output_path.write_bytes(response.content)

    print(f"Download successful: {output_path}")
    print(f"Response size: {len(response.content):,} bytes")
    print(f"Top-level type: {type(payload).__name__}")

    
    # 4. Validate and inspect the dataset structure.
    if not isinstance(payload, list):
        raise TypeError(
            f"Expected a list, got {type(payload).__name__}"
        )

    if len(payload) != 1:
        raise ValueError(
            f"Expected one dataset object, got {len(payload)}"
        )

    dataset = payload[0]

    if not isinstance(dataset, dict):
        raise TypeError("The dataset object must be a dictionary")

    metadata = dataset.get("metadata")
    records = dataset.get("data")

    if not isinstance(metadata, list):
        raise ValueError("Missing or invalid 'metadata' list")

    if not isinstance(records, list):
        raise ValueError("Missing or invalid 'data' list")

    print("\n=== DATASET STRUCTURE ===")
    print("Dataset keys:", list(dataset.keys()))
    print("Metadata items:", len(metadata))
    print("Data records:", len(records))

    # 5. Read the metadata.
    print("\n=== METADATA ===")

    for index, item in enumerate(metadata, start=1):
        if not isinstance(item, dict):
            print(f"{index}. Unexpected metadata type")
            continue

        name = (
            item.get("name_en")
            or item.get("name_uz")
            or "<unnamed>"
        )

        value = (
            item.get("value_en")
            or item.get("value_uz")
            or "<no value>"
        )

        print(f"{index:02}. {name}: {value}")

    # 6. Inspect a few actual records.
    print("\n=== SAMPLE RECORDS ===")

    sample_records = records[:3]

    for index, record in enumerate(sample_records, start=1):
        print(f"\nRecord {index}:")
        print(
            json.dumps(
                record,
                indent=2,
                ensure_ascii=False,
                default=str,
            )[:2000]
        )


if __name__ == "__main__":
    main()
