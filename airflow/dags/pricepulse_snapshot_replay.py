import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pendulum
from airflow.sdk import dag, get_current_context, task


PROJECT_ROOT = Path("/opt/pricepulse")
REPLAY_SCRIPT = PROJECT_ROOT / "scripts" / "replay_snapshot.py"


@dag(
    dag_id="pricepulse_snapshot_replay",
    schedule=None,
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={
        "retries": 0,
        "execution_timeout": timedelta(minutes=30),
    },
    tags=["pricepulse", "replay", "data-engineering"],
    description=(
        "Replay a registered historical snapshot in isolation, "
        "without loading it into live analytics tables."
    ),
)
def pricepulse_snapshot_replay():

    @task
    def replay_registered_snapshot():
        context = get_current_context()
        dag_run = context["dag_run"]
        conf = dag_run.conf or {}

        if not isinstance(conf, dict):
            raise ValueError("DAG configuration must be a JSON object")

        filename = conf.get("snapshot_filename")

        if not isinstance(filename, str) or not filename.strip():
            raise ValueError(
                "Missing snapshot_filename. Supply a registered "
                "snapshot filename in the DAG run configuration."
            )

        if not REPLAY_SCRIPT.is_file():
            raise FileNotFoundError(
                f"Replay script is missing: {REPLAY_SCRIPT}. "
                "Rebuild the Airflow image."
            )

        required = (
            "DB_HOST",
            "DB_PORT",
            "DB_NAME",
            "DB_USER",
            "DB_PASSWORD",
        )
        missing = [key for key in required if not os.getenv(key)]

        if missing:
            raise RuntimeError(
                "Missing required database environment variables: "
                + ", ".join(missing)
            )

        command = [
            sys.executable,
            str(REPLAY_SCRIPT),
            "--snapshot",
            filename,
            "--trigger-source",
            "airflow",
            "--airflow-dag-run-id",
            dag_run.run_id,
        ]

        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "replay_snapshot.py failed with exit code "
                f"{completed.returncode}"
            )

    replay_registered_snapshot()


pricepulse_snapshot_replay()
