import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pendulum
from airflow.sdk import dag, task


PROJECT_ROOT = Path("/opt/pricepulse")
PYTHON = sys.executable


def run_script(script_name: str, *args: str) -> None:
    script_path = PROJECT_ROOT / "scripts" / script_name

    subprocess.run(
        [PYTHON, str(script_path), *args],
        cwd=PROJECT_ROOT,
        check=True,
    )


def require_database_environment() -> None:
    required = (
        "DB_HOST",
        "DB_PORT",
        "DB_NAME",
        "DB_USER",
        "DB_PASSWORD",
    )
    missing = [name for name in required if not os.getenv(name)]

    if missing:
        raise RuntimeError(
            "Missing required database variables: "
            + ", ".join(missing)
        )


@dag(
    dag_id="pricepulse_pipeline",
    schedule="0 6 20 * *",
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={
        "retries": 1,
        "retry_delay": timedelta(minutes=1),
    },
    tags=["pricepulse", "data-engineering"],
    description="Official Uzbekistan price ingestion and analytics pipeline",
)
def pricepulse_pipeline():

    @task
    def extract_source() -> str:
        script_path = PROJECT_ROOT / "scripts" / "extract_source.py"

        result = subprocess.run(
            [PYTHON, str(script_path)],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")

        if result.stdout:
            print(result.stdout, end="")

        paths = [
            line.partition("=")[2]
            for line in result.stdout.splitlines()
            if line.startswith("SNAPSHOT_PATH=")
        ]

        if len(paths) != 1:
            raise RuntimeError(
                "Extraction did not return exactly one snapshot path"
            )

        snapshot_path = paths[0]

        if not Path(snapshot_path).is_file():
            raise FileNotFoundError(
                f"Extracted snapshot does not exist: {snapshot_path}"
            )

        return snapshot_path

    @task
    def register_snapshot_history(snapshot_path: str) -> None:
        if not snapshot_path:
            raise ValueError("Snapshot path is required for registration")

        require_database_environment()
        run_script("load_snapshot_history.py")

    @task
    def normalize_source(snapshot_path: str) -> None:
        run_script(
            "normalize_source.py",
            "--source",
            snapshot_path,
        )

    @task
    def audit_data() -> None:
        run_script("audit_data.py")

    @task
    def clean_prices() -> None:
        run_script("clean_prices.py")

    @task
    def run_tests() -> None:
        subprocess.run(
            [
                PYTHON,
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
            ],
            cwd=PROJECT_ROOT,
            check=True,
        )

    @task
    def load_to_database() -> None:
        require_database_environment()
        run_script("load_to_postgres.py")

    snapshot_path = extract_source()

    # Registration and transformations use the same extracted snapshot.
    history = register_snapshot_history(snapshot_path)
    normalized = normalize_source(snapshot_path)

    audited = audit_data()
    cleaned = clean_prices()
    tests = run_tests()
    load = load_to_database()

    normalized >> audited >> cleaned >> tests >> load
    history >> load


pricepulse_pipeline()
