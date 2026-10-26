
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

        # Keep the script's logs visible in Airflow task logs.
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")

        if result.stdout:
            print(result.stdout, end="")

        markers = [
            line.partition("=")[2]
            for line in result.stdout.splitlines()
            if line.startswith("SNAPSHOT_PATH=")
        ]

        if len(markers) != 1:
            raise RuntimeError(
                "Extraction did not return exactly one snapshot path"
            )

        snapshot_path = markers[0]

        if not Path(snapshot_path).is_file():
            raise FileNotFoundError(
                f"Extracted snapshot does not exist: {snapshot_path}"
            )

        return snapshot_path


    @task
    def normalize_source(snapshot_path: str):
        run_script(
            "normalize_source.py",
            "--source",
            snapshot_path,
        )

    @task
    def audit_data():
        run_script("audit_data.py")

    @task
    def clean_prices():
        run_script("clean_prices.py")

    @task
    def run_tests():
        subprocess.run(
            [PYTHON, "-m", "pytest", "-q"],
            cwd=PROJECT_ROOT,
            check=True,
        )

    @task
    def load_to_database():
        required_variables = [
            "DB_HOST",
            "DB_NAME",
            "DB_USER",
            "DB_PASSWORD",
        ]

        missing = [
            name
            for name in required_variables
            if not os.getenv(name)
        ]

        if missing:
            raise RuntimeError(
                "Missing required database variables: "
                + ", ".join(missing)
            )

        run_script("load_to_postgres.py")

    # Defining the dependency graph does not run the scripts here.
    # Airflow schedules and executes these tasks at runtime.
    snapshot_path = extract_source()
    normalize = normalize_source(snapshot_path)

    audit = audit_data()
    clean = clean_prices()
    tests = run_tests()
    load = load_to_database()

    normalize >> audit >> clean >> tests >> load

pricepulse_pipeline()
