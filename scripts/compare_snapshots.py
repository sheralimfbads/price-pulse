
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"


def parse_period(column: str) -> str | None:
    """Convert source keys such as 2021-М01 into YYYY-MM."""
    if not re.match(r"^\d{4}-", column):
        return None

    parts = re.findall(r"\d+", column)

    if (
        len(parts) != 2
        or len(parts[0]) != 4
        or len(parts[1]) != 2
    ):
        return None

    year, month = map(int, parts)

    if not 1 <= month <= 12:
        raise ValueError(f"Invalid period column: {column!r}")

    return f"{year:04d}-{month:02d}"


def load_snapshot(path: Path) -> dict:
    raw_bytes = path.read_bytes()
    payload = json.loads(raw_bytes)

    if (
        not isinstance(payload, list)
        or len(payload) != 1
        or not isinstance(payload[0], dict)
    ):
        raise ValueError(f"Unexpected structure in {path.name}")

    dataset = payload[0]
    records = dataset.get("data")
    metadata = dataset.get("metadata")

    if not isinstance(records, list):
        raise ValueError(f"Missing data records in {path.name}")

    if not isinstance(metadata, list):
        raise ValueError(f"Missing metadata in {path.name}")

    products = {}
    observations = {}

    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Unexpected non-object product record")

        code = record.get("Code")

        if not isinstance(code, str) or not code.strip():
            raise ValueError("Missing product code")

        if code in products:
            raise ValueError(f"Duplicate product code: {code}")

        products[code] = {
            "uz": record.get("Klassifikator"),
            "ru": record.get("Klassifikator_ru"),
            "en": record.get("Klassifikator_en"),
            "uzc": record.get("Klassifikator_uzc"),
        }

        for column, value in record.items():
            period = parse_period(column)

            if period is None:
                continue

            key = (code, period)

            if key in observations:
                raise ValueError(
                    f"Duplicate product-month observation: {key}"
                )

            observations[key] = value

    modified_dates = []

    for item in metadata:
        if not isinstance(item, dict):
            continue

        name = str(item.get("name_en", "")).casefold()

        if "last modified date" in name:
            modified_dates.append(
                item.get("value_en") or item.get("value_uz")
            )

    # Hash the original bytes separately from the normalized content.
    raw_hash = hashlib.sha256(raw_bytes).hexdigest()

    semantic_payload = {
        "products": products,
        "observations": [
            [code, period, value]
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
        "name": path.name,
        "raw_hash": raw_hash,
        "semantic_hash": semantic_hash,
        "products": products,
        "observations": observations,
        "modified_dates": sorted(
            {str(value) for value in modified_dates if value}
        ),
    }


def main() -> None:
    files = sorted(RAW_DIR.glob("official_prices_*.json"))

    if not files:
        raise FileNotFoundError(
            f"No raw snapshots found in {RAW_DIR}"
        )

    snapshots = [load_snapshot(path) for path in files]

    print("=== SNAPSHOT INVENTORY ===")

    for snapshot in snapshots:
        print(f"\nFile: {snapshot['name']}")
        print(f"Products: {len(snapshot['products'])}")
        print(f"Product-month observations: "
              f"{len(snapshot['observations'])}")
        print(f"Source modification dates: "
              f"{snapshot['modified_dates']}")
        print(f"Raw SHA-256: {snapshot['raw_hash'][:16]}...")
        print(f"Semantic SHA-256: {snapshot['semantic_hash'][:16]}...")

    print("\n=== CONSECUTIVE SNAPSHOT COMPARISON ===")

    if len(snapshots) == 1:
        print("Only one snapshot exists; nothing to compare.")
        return

    for previous, current in zip(snapshots, snapshots[1:]):
        old = previous["observations"]
        new = current["observations"]

        old_keys = set(old)
        new_keys = set(new)

        added = new_keys - old_keys
        removed = old_keys - new_keys

        changed = {
            key
            for key in old_keys & new_keys
            if old[key] != new[key]
        }

        product_names_changed = {
            code
            for code in (
                set(previous["products"]) & set(current["products"])
            )
            if previous["products"][code] != current["products"][code]
        }

        print(f"\nPrevious: {previous['name']}")
        print(f"Current:  {current['name']}")
        print(f"New observations: {len(added)}")
        print(f"Removed observations: {len(removed)}")
        print(f"Changed prices: {len(changed)}")
        print(f"Products with changed names: "
              f"{len(product_names_changed)}")
        print(f"Raw content identical: "
              f"{previous['raw_hash'] == current['raw_hash']}")
        print(f"Normalized content identical: "
              f"{previous['semantic_hash'] == current['semantic_hash']}")

        for code, period in sorted(changed)[:5]:
            print(
                f"  Changed: product={code}, month={period}, "
                f"{old[(code, period)]!r} -> {new[(code, period)]!r}"
            )


if __name__ == "__main__":
    main()
