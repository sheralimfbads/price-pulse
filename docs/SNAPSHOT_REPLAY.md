# PricePulse: Historical Snapshot Replay

## Purpose

Replay a registered official-price snapshot for reproducibility checks,
historical debugging, and transformation validation.

Replay is separate from production loading. It must not write historical
replay data into live staging or analytics tables.

## Workflow

1. Validate the requested timestamped filename.
2. Verify registration and source hashes in PostgreSQL.
3. Normalize into a unique replay directory.
4. Audit and clean the data.
5. Run automated tests.
6. Verify source lineage and row counts.
7. Calculate output hashes.
8. Record success or failure in PostgreSQL.

Each execution has its own UUID and output directory.

## Docker Compose

Run a registered snapshot with:

    docker compose run --rm --build pipeline \
      python scripts/replay_snapshot.py \
      --snapshot official_prices_20261020T105154Z.json

The runner uses DB_HOST, DB_PORT, DB_NAME, DB_USER, and DB_PASSWORD
from the environment. Never commit real credentials.

## Airflow

Trigger pricepulse_snapshot_replay with this run configuration:

    {"snapshot_filename": "official_prices_20261020T105154Z.json"}

The replay DAG invokes the same runner as the CLI. The scheduled
pricepulse_pipeline remains the production ingestion workflow.

## Audit history

Query audit.snapshot_replay_run to inspect replay IDs, source filenames,
trigger source, status, row counts, output hashes, timestamps, and errors.

Raw SHA-256 identifies exact file bytes. Semantic SHA-256 identifies
canonicalized logical data, so differently serialized files can represent
the same dataset.

## Data-quality decision

The current dataset contains six zero-price observations. PricePulse
preserves the source values, marks them zero_marked_unavailable, and
leaves their analytical prices missing. This is a project assumption,
not an authoritative interpretation by the source authority.

## Tests

Run the automated suite with:

    python -m pytest -q
