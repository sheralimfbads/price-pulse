from pathlib import Path
import subprocess
import sys
import time


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


PIPELINE_STEPS = [
    (
        "Extract official source",
        [PYTHON, "scripts/extract_source.py"],
    ),
    (
        "Register source snapshot history",
        [PYTHON, "scripts/load_snapshot_history.py"],
    ),
    (
        "Normalize source data",
        [PYTHON, "scripts/normalize_source.py"],
    ),
    (
        "Audit normalized data",
        [PYTHON, "scripts/audit_data.py"],
    ),
    (
        "Clean analytical prices",
        [PYTHON, "scripts/clean_prices.py"],
    ),
    (
        "Run automated tests",
        [
            PYTHON,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "-m",
            "not integration and not e2e",
        ],
    ),
    (
        "Load data into PostgreSQL",
        [PYTHON, "scripts/load_to_postgres.py"],
    ),
]


def main() -> None:
    pipeline_started = time.monotonic()

    print("=" * 60, flush=True)
    print("PRICEPULSE DATA PIPELINE", flush=True)
    print("=" * 60, flush=True)

    for step_number, (name, command) in enumerate(
        PIPELINE_STEPS,
        start=1,
    ):
        print(
            f"\n[{step_number}/{len(PIPELINE_STEPS)}] {name}",
            flush=True,
        )

        step_started = time.monotonic()

        try:
            subprocess.run(
                command,
                cwd=PROJECT_ROOT,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            print(f"\nPIPELINE FAILED: {name}", flush=True)
            print(f"Command exit code: {exc.returncode}", flush=True)
            raise SystemExit(exc.returncode) from exc

        elapsed = time.monotonic() - step_started
        print(f"Step completed in {elapsed:.2f} seconds", flush=True)

    total_elapsed = time.monotonic() - pipeline_started

    print("\n" + "=" * 60, flush=True)
    print("PIPELINE COMPLETED SUCCESSFULLY", flush=True)
    print(f"Total runtime: {total_elapsed:.2f} seconds", flush=True)
    print("=" * 60, flush=True)


if __name__ == "__main__":
    main()
