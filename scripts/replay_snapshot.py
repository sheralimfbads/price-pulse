import argparse
import csv
import hashlib
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
REPLAY_ROOT = PROCESSED_DIR / "replays"

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "pricepulse"),
    "user": os.getenv("DB_USER", "pricepulse_dev"),
}

SNAPSHOT_FILENAME_PATTERN = re.compile(
    r"official_prices_\d{8}T\d{6}Z\.json"
)

# Reuse the canonical semantic-hash implementation. Do not create
# a second, potentially inconsistent implementation of snapshot identity.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.load_snapshot_history import (  # noqa: E402
    SEMANTIC_HASH_VERSION,
    read_snapshot,
)


def connect_to_database():
    import psycopg

    password = os.getenv("DB_PASSWORD")
    if not password:
        raise RuntimeError(
            "DB_PASSWORD must be set for snapshot replay"
        )

    return psycopg.connect(
        **DB_CONFIG,
        password=password,
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def csv_row_count(
    path: Path,
    expected_snapshot: str | None = None,
) -> int:
    if not path.is_file():
        raise FileNotFoundError(
            f"Expected output CSV does not exist: {path}"
        )

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {path}")

        if (
            expected_snapshot is not None
            and "source_snapshot" not in reader.fieldnames
        ):
            raise ValueError(
                f"CSV is missing source_snapshot lineage: {path}"
            )

        count = 0

        for row in reader:
            count += 1

            if (
                expected_snapshot is not None
                and row.get("source_snapshot") != expected_snapshot
            ):
                raise ValueError(
                    f"Snapshot lineage mismatch in {path}: "
                    f"expected {expected_snapshot!r}, "
                    f"got {row.get('source_snapshot')!r}"
                )

        return count


def run_step(name: str, command: list[str]) -> None:
    print(f"\n=== {name} ===", flush=True)

    subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=True,
    )


def validate_snapshot(snapshot_filename: str, conn) -> dict:
    # Accept a filename, never an arbitrary filesystem path.
    if (
        snapshot_filename != Path(snapshot_filename).name
        or "/" in snapshot_filename
        or "\\" in snapshot_filename
        or not SNAPSHOT_FILENAME_PATTERN.fullmatch(snapshot_filename)
    ):
        raise ValueError(
            "Provide a timestamped snapshot filename such as "
            "'official_prices_20261020T105154Z.json'. "
            "Filesystem paths are not accepted."
        )

    raw_path = RAW_DIR / snapshot_filename
    resolved_path = raw_path.resolve()

    # Keep snapshot reads inside the designated raw-data directory.
    if (
        resolved_path.parent != RAW_DIR.resolve()
        or resolved_path.name != snapshot_filename
    ):
        raise ValueError(
            "Snapshot must be a regular file directly inside data/raw/"
        )

    if not resolved_path.is_file():
        raise FileNotFoundError(
            f"Snapshot file not found: {snapshot_filename}"
        )

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                snapshot_id,
                raw_sha256,
                semantic_sha256,
                semantic_hash_version,
                product_count,
                period_count,
                observation_count
            FROM audit.source_snapshot
            WHERE snapshot_filename = %s
            """,
            (snapshot_filename,),
        )

        registered = cur.fetchone()

    if registered is None:
        raise ValueError(
            f"Snapshot is not registered in PostgreSQL: "
            f"{snapshot_filename}"
        )

    (
        snapshot_id,
        registered_raw_hash,
        registered_semantic_hash,
        registered_hash_version,
        registered_product_count,
        registered_period_count,
        registered_observation_count,
    ) = registered

    if registered_hash_version != SEMANTIC_HASH_VERSION:
        raise ValueError(
            "Snapshot registry uses semantic-hash version "
            f"{registered_hash_version}; this runner requires "
            f"version {SEMANTIC_HASH_VERSION}. "
            "Upgrade the registered snapshot hashes first."
        )

    # Recalculate both hashes from the actual local file.
    snapshot = read_snapshot(resolved_path)

    if snapshot["raw_sha256"] != registered_raw_hash:
        raise ValueError(
            "Raw SHA-256 mismatch. The local file does not match "
            "the registered snapshot."
        )

    if snapshot["semantic_sha256"] != registered_semantic_hash:
        raise ValueError(
            "Semantic SHA-256 mismatch. The file's logical data "
            "does not match its registered identity."
        )

    actual_counts = (
        len(snapshot["products"]),
        snapshot["period_count"],
        snapshot["observation_count"],
    )

    registered_counts = (
        registered_product_count,
        registered_period_count,
        registered_observation_count,
    )

    if actual_counts != registered_counts:
        raise ValueError(
            "Snapshot count mismatch: "
            f"registered={registered_counts}, actual={actual_counts}"
        )

    return {
        "snapshot_id": snapshot_id,
        "raw_sha256": snapshot["raw_sha256"],
        "semantic_sha256": snapshot["semantic_sha256"],
        "semantic_hash_version": registered_hash_version,
        "observation_count": snapshot["observation_count"],
        "raw_path": resolved_path,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Replay a registered PricePulse source snapshot "
            "without modifying live analytics tables."
        )
    )

    parser.add_argument(
        "--snapshot",
        required=True,
        help="Exact registered snapshot filename inside data/raw/",
    )

    parser.add_argument(
        "--trigger-source",
        choices=("cli", "airflow"),
        default="cli",
        help="Execution source recorded in the audit table",
    )

    parser.add_argument(
        "--airflow-dag-run-id",
        default=None,
        help="Airflow DAG run ID when invoked by Airflow",
    )

    args = parser.parse_args()

    replay_run_id = uuid.uuid4()

    # Only valid timestamped filenames influence the directory name.
    # Invalid requests get a safe directory name and are still audited.
    if SNAPSHOT_FILENAME_PATTERN.fullmatch(args.snapshot):
        folder_name = Path(args.snapshot).stem
    else:
        folder_name = "invalid-request"

    output_dir = REPLAY_ROOT / folder_name / str(replay_run_id)
    output_dir_relative = output_dir.relative_to(PROJECT_ROOT).as_posix()

    normalized_path = output_dir / "official_prices_long.csv"
    analytics_path = output_dir / "official_prices_analytics.csv"

    conn = connect_to_database()
    run_registered = False

    try:
        # Commit the initial record before any validation or ETL work.
        # This allows a rejected snapshot request to be audited too.
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO audit.snapshot_replay_run (
                    replay_run_id,
                    requested_snapshot_filename,
                    trigger_source,
                    airflow_dag_run_id,
                    output_directory
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    replay_run_id,
                    args.snapshot,
                    args.trigger_source,
                    args.airflow_dag_run_id,
                    output_dir_relative,
                ),
            )

        conn.commit()
        run_registered = True

        print(f"Replay run ID: {replay_run_id}", flush=True)
        print(f"Requested snapshot: {args.snapshot}", flush=True)

        # Validate identity against the authoritative snapshot registry.
        source = validate_snapshot(args.snapshot, conn)

        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE audit.snapshot_replay_run
                SET
                    snapshot_id = %s,
                    source_raw_sha256 = %s,
                    source_semantic_sha256 = %s,
                    semantic_hash_version = %s
                WHERE replay_run_id = %s
                """,
                (
                    source["snapshot_id"],
                    source["raw_sha256"],
                    source["semantic_sha256"],
                    source["semantic_hash_version"],
                    replay_run_id,
                ),
            )

        conn.commit()

        output_dir.mkdir(parents=True, exist_ok=False)

        python = sys.executable
        raw_path = str(source["raw_path"])

        # All outputs go to this replay's unique directory.
        run_step(
            "Normalize historical snapshot",
            [
                python,
                str(PROJECT_ROOT / "scripts" / "normalize_source.py"),
                "--source",
                raw_path,
                "--output",
                str(normalized_path),
            ],
        )

        run_step(
            "Audit normalized data",
            [
                python,
                str(PROJECT_ROOT / "scripts" / "audit_data.py"),
                "--input",
                str(normalized_path),
            ],
        )

        run_step(
            "Clean analytical prices",
            [
                python,
                str(PROJECT_ROOT / "scripts" / "clean_prices.py"),
                "--input",
                str(normalized_path),
                "--output",
                str(analytics_path),
            ],
        )

        run_step(
            "Run automated unit tests",
            [
                python,
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                "-m",
                "not integration and not e2e",
            ],
        )

        # Enforce row counts and snapshot lineage before declaring success.
        normalized_rows = csv_row_count(
            normalized_path,
            expected_snapshot=args.snapshot,
        )

        analytics_rows = csv_row_count(
            analytics_path,
            expected_snapshot=args.snapshot,
        )

        expected_rows = source["observation_count"]

        if normalized_rows != expected_rows:
            raise ValueError(
                f"Normalized row count mismatch: "
                f"expected {expected_rows}, got {normalized_rows}"
            )

        if analytics_rows != normalized_rows:
            raise ValueError(
                f"Analytics row count mismatch: "
                f"normalized={normalized_rows}, "
                f"analytics={analytics_rows}"
            )

        normalized_hash = sha256_file(normalized_path)
        analytics_hash = sha256_file(analytics_path)

        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE audit.snapshot_replay_run
                SET
                    status = 'succeeded',
                    normalized_row_count = %s,
                    analytics_row_count = %s,
                    normalized_sha256 = %s,
                    analytics_sha256 = %s,
                    finished_at_utc = CURRENT_TIMESTAMP,
                    error_message = NULL
                WHERE replay_run_id = %s
                  AND status = 'running'
                """,
                (
                    normalized_rows,
                    analytics_rows,
                    normalized_hash,
                    analytics_hash,
                    replay_run_id,
                ),
            )

            if cur.rowcount != 1:
                raise RuntimeError(
                    "Could not mark replay run as succeeded"
                )

        conn.commit()

        print("\n" + "=" * 60, flush=True)
        print("SNAPSHOT REPLAY SUCCEEDED", flush=True)
        print(f"Replay run ID: {replay_run_id}", flush=True)
        print(f"Output directory: {output_dir_relative}", flush=True)
        print(f"Normalized rows: {normalized_rows:,}", flush=True)
        print(f"Analytics rows: {analytics_rows:,}", flush=True)
        print(f"Normalized SHA-256: {normalized_hash}", flush=True)
        print(f"Analytics SHA-256: {analytics_hash}", flush=True)
        print("=" * 60, flush=True)

    except Exception as exc:
        # Preserve the original failure, but record it in the audit log.
        conn.rollback()

        if run_registered:
            error_message = f"{type(exc).__name__}: {exc}"[:4000]

            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE audit.snapshot_replay_run
                    SET
                        status = 'failed',
                        finished_at_utc = CURRENT_TIMESTAMP,
                        error_message = %s
                    WHERE replay_run_id = %s
                      AND status = 'running'
                    """,
                    (error_message, replay_run_id),
                )

            conn.commit()

        print(
            f"\nSNAPSHOT REPLAY FAILED: {replay_run_id}",
            file=sys.stderr,
            flush=True,
        )
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    main()
