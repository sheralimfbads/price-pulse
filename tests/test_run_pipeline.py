
import subprocess
import sys

import pytest

from scripts import run_pipeline


def test_pipeline_runs_all_steps(monkeypatch):
    calls = []

    def fake_run(command, cwd, check):
        calls.append(command)

    monkeypatch.setattr(
        run_pipeline,
        "PIPELINE_STEPS",
        [
            ("Step A", [sys.executable, "a.py"]),
            ("Step B", [sys.executable, "b.py"]),
        ],
    )

    monkeypatch.setattr(
        run_pipeline.subprocess,
        "run",
        fake_run,
    )

    run_pipeline.main()

    assert len(calls) == 2
    assert calls[0][1] == "a.py"
    assert calls[1][1] == "b.py"


def test_pipeline_stops_when_a_step_fails(monkeypatch):
    calls = []

    def fake_run(command, cwd, check):
        calls.append(command)

        if command[1] == "bad.py":
            raise subprocess.CalledProcessError(
                returncode=2,
                cmd=command,
            )

    monkeypatch.setattr(
        run_pipeline,
        "PIPELINE_STEPS",
        [
            ("Step A", [sys.executable, "a.py"]),
            ("Step B", [sys.executable, "bad.py"]),
            ("Step C", [sys.executable, "c.py"]),
        ],
    )

    monkeypatch.setattr(
        run_pipeline.subprocess,
        "run",
        fake_run,
    )

    with pytest.raises(SystemExit) as exc:
        run_pipeline.main()

    assert exc.value.code == 2
    assert len(calls) == 2
    assert calls[-1][1] == "bad.py"
