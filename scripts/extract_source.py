
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"

SOURCE_URL = (
    "https://api.siat.stat.uz/media/uploads/"
    "sdmx/sdmx_data_1308.json"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger("pricepulse.extract")


def main() -> None:
    logger.info("Requesting official price dataset")

    try:
        response = requests.get(
            SOURCE_URL,
            headers={
                "User-Agent": "PricePulse/0.1 (educational data project)"
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()

    except requests.RequestException:
        logger.exception("HTTP request failed")
        raise

    except ValueError:
        logger.exception("Source did not return valid JSON")
        raise

    # Validate the basic structure before preserving the snapshot.
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
        raise ValueError("Source metadata must be a list")

    if not isinstance(records, list) or not records:
        raise ValueError("Source data must be a non-empty list")

    fetched_at = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    output_path = RAW_DIR / f"official_prices_{fetched_at}.json"
    temporary_path = output_path.with_suffix(".json.tmp")

    # Never silently overwrite an existing snapshot.
    if output_path.exists():
        raise FileExistsError(
            f"Snapshot already exists: {output_path.name}"
        )

    try:
        temporary_path.write_bytes(response.content)
        temporary_path.replace(output_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise

    logger.info(
        "Snapshot saved | file=%s | bytes=%d | products=%d | metadata_items=%d",
        output_path.name,
        len(response.content),
        len(records),
        len(metadata),
    )
    print(f"SNAPSHOT_PATH={output_path.resolve()}", flush=True)


if __name__ == "__main__":
    main()
