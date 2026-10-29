"""
Tests for the Airflow DAG definitions.

These tests validate that the DAGs import correctly, have the expected
structure, and are correctly configured for Apache Airflow 3.x.

These tests are skipped automatically when apache-airflow is not installed,
which is the case in the local developer venv (Airflow runs in Docker).

Run inside the Airflow container with:
    docker compose exec airflow pytest /opt/pricepulse/tests/test_dags.py -v
"""

from __future__ import annotations

import os
from pathlib import Path
import pytest

# ---------------------------------------------------------------------------
# Gracefully skip when Airflow is not installed (local dev venv).
# ---------------------------------------------------------------------------
try:
    from airflow.models import DagBag
    AIRFLOW_AVAILABLE = True
except ImportError:
    AIRFLOW_AVAILABLE = False


skip_without_airflow = pytest.mark.skipif(
    not AIRFLOW_AVAILABLE,
    reason="apache-airflow is not installed in this environment (tests run inside Airflow container)",
)


def _load_dagbag():
    dag_folder = Path("/opt/airflow/dags")
    if not dag_folder.is_dir():
        dag_folder = Path(__file__).resolve().parents[1] / "airflow" / "dags"
    return DagBag(dag_folder=str(dag_folder))


# ---------------------------------------------------------------------------
# DAG import smoke test
# ---------------------------------------------------------------------------

@skip_without_airflow
def test_no_import_errors():
    """All DAGs must load without import errors."""
    bag = _load_dagbag()
    assert bag.import_errors == {}, (
        f"DAG import errors:\n"
        + "\n".join(f"{k}: {v}" for k, v in bag.import_errors.items())
    )


@skip_without_airflow
def test_pipeline_dag_exists():
    bag = _load_dagbag()
    assert "pricepulse_pipeline" in bag.dag_ids, (
        "pricepulse_pipeline DAG not found; check DAG file and dag_id"
    )


@skip_without_airflow
def test_replay_dag_exists():
    bag = _load_dagbag()
    assert "pricepulse_snapshot_replay" in bag.dag_ids, (
        "pricepulse_snapshot_replay DAG not found; check DAG file and dag_id"
    )


# ---------------------------------------------------------------------------
# Pipeline DAG structure
# ---------------------------------------------------------------------------

@skip_without_airflow
class TestPipelineDag:
    @classmethod
    def setup_class(cls):
        cls.dag = _load_dagbag().get_dag("pricepulse_pipeline")

    def test_has_expected_tasks(self):
        task_ids = {t.task_id for t in self.dag.tasks}
        expected = {
            "extract_source",
            "register_snapshot_history",
            "normalize_source",
            "audit_data",
            "clean_prices",
            "load_to_database",
        }
        missing = expected - task_ids
        assert not missing, f"Missing tasks: {missing}"

    def test_schedule_is_monthly(self):
        schedule = getattr(self.dag, "schedule", getattr(self.dag, "schedule_interval", None))
        assert schedule == "0 6 20 * *"

    def test_catchup_disabled(self):
        assert self.dag.catchup is False

    def test_max_active_runs(self):
        assert self.dag.max_active_runs == 1

    def test_load_depends_on_clean_data_and_snapshot_history(self):
        """Only validated data with registered lineage may reach the loader."""
        load_task = self.dag.get_task("load_to_database")
        upstream_ids = {t.task_id for t in load_task.upstream_list}
        assert "clean_prices" in upstream_ids
        assert "register_snapshot_history" in upstream_ids


# ---------------------------------------------------------------------------
# Replay DAG structure
# ---------------------------------------------------------------------------

@skip_without_airflow
class TestReplayDag:
    @classmethod
    def setup_class(cls):
        cls.dag = _load_dagbag().get_dag("pricepulse_snapshot_replay")

    def test_has_replay_task(self):
        task_ids = {t.task_id for t in self.dag.tasks}
        assert "replay_registered_snapshot" in task_ids

    def test_schedule_is_none(self):
        schedule = getattr(self.dag, "schedule", getattr(self.dag, "schedule_interval", None))
        assert schedule is None

    def test_catchup_disabled(self):
        assert self.dag.catchup is False

    def test_no_retries_by_default(self):
        """Replay must not silently retry on a bad snapshot."""
        replay_task = self.dag.get_task("replay_registered_snapshot")
        assert replay_task.retries == 0
