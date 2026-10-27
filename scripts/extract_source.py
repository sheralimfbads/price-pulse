
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"

SOURCE_URL = (
    "https://api.siat.stat.uz/media/uploads/"
    "sdmx/sdmx_data_1308.json"
)

REQUEST_TIMEOUT_SECONDS = 30
RETRY_TOTAL = 3
RETRY_BACKOFF_SECONDS = 1.5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger("pricepulse.extract")


def build_session() -> requests.Session:
    retry = Retry(
        total=RETRY_TOTAL,
        connect=RETRY_TOTAL,
        read=RETRY_TOTAL,
        backoff_factor=RETRY_BACKOFF_SECONDS,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def validate_payload(payload: object) -> tuple[list, list]:
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

    return metadata, records


def save_snapshot(content: bytes, fetched_at: str) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RAW_DIR / f"official_prices_{fetched_at}.json"
    temporary_path = output_path.with_suffix(".json.tmp")

    if output_path.exists():
        raise FileExistsError(
            f"Snapshot already exists: {output_path.name}"
        )

    try:
        temporary_path.write_bytes(content)
        temporary_path.replace(output_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise

    return output_path


def main() -> None:
    logger.info("Requesting official price dataset")

    try:
        session = build_session()
        response = session.get(
            SOURCE_URL,
            headers={
                "User-Agent": "PricePulse/0.1 (educational data project)"
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        if not response.content:
            raise ValueError("Source returned an empty response")

        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise ValueError("Source did not return valid JSON") from exc

        metadata, records = validate_payload(payload)

    except requests.RequestException:
        logger.exception("HTTP request failed")
        raise

    fetched_at = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = save_snapshot(response.content, fetched_at)

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
