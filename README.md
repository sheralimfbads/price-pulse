# PricePulse — Uzbekistan Price Data Engineering

PricePulse is a learning-focused data engineering portfolio project built around official monthly average prices for selected goods in Uzbekistan. It is developed as one evolving system: each added component addresses a real pipeline requirement and is documented and tested.

The project includes a Python ingestion and transformation pipeline, PostgreSQL staging and analytics models, source-snapshot history, deterministic historical replay, Docker Compose services, and Airflow orchestration.

## Project status

**Implemented and exercised locally:**

- Fetching and preserving timestamped raw JSON snapshots from the official source.
- Registering snapshot identity and history, including semantic hashes.
- Normalizing monthly source data to one row per product and month.
- Auditing source data and cleaning analytical prices while preserving source values.
- Loading data into PostgreSQL staging and a product/month star schema.
- Running the current ingestion pipeline through Docker Compose and Airflow.
- Replaying a registered historical source snapshot into an isolated output directory, with replay results recorded in the audit schema.
- Running automated Python tests and GitHub Actions CI.

This is still an educational portfolio project, not a production service. Cloud deployment, operational monitoring, production-grade alerting, and broader integration testing remain future work.

## Data source

- **Dataset:** *Dynamics of average prices of some goods in markets and stores*.
- **Publisher:** National Statistics Committee of the Republic of Uzbekistan.
- **Unit:** soums (UZS) per kilogram.
- **Frequency:** monthly.
- **JSON endpoint:** <https://api.siat.stat.uz/media/uploads/sdmx/sdmx_data_1308.json>
- **Statistics portal:** <https://stat.uz/en/official-statistics/prices-and-indexes>

The inspected snapshot fetched on 20 October 2026 contained 41 products and 69 monthly periods, covering January 2021 through September 2026. Counts below describe that snapshot and can change when the source is updated.

## Architecture and data flow

```text
Official statistics JSON API
            |
            v
Timestamped raw JSON snapshot
            |
            v
Snapshot registry + semantic hashes
            |
            v
Normalize -> Audit -> Clean -> Automated tests
            |
            v
PostgreSQL staging tables
            |
            v
Analytics star schema
(dim_product, dim_month, fact_monthly_official_price)
```

The `audit` schema records source snapshots and their product/price observations. A historical replay validates a selected registered snapshot, processes it into a unique replay directory, records success or failure, and **does not load replay output into the live staging or analytics tables**.

Airflow has two distinct responsibilities:

- `pricepulse_pipeline` runs the current ingestion pipeline.
- `pricepulse_snapshot_replay` is a manually triggered DAG that replays a registered snapshot supplied through the DAG run configuration.

## Current observed data counts

| Check | Observed value |
|---|---:|
| Products | 41 |
| Monthly periods | 69 |
| Normalized product-month observations | 2,829 |
| `analytics.dim_product` | 41 |
| `analytics.dim_month` | 69 |
| `analytics.fact_monthly_official_price` | 2,829 |
| Positive observed prices | 2,823 |
| Zero-marked unavailable prices | 6 |
| Duplicate product-month keys | 0 |

### Zero-price handling

Six observations in the inspected source snapshot had a price of zero. The pipeline preserves each original source value in `source_price_uzs_per_kg`, sets the analytical price to missing, and assigns `price_status = 'zero_marked_unavailable'`. The other 2,823 observations are marked `observed`.

This treatment is a documented **project assumption**, not a claim that the publisher formally defines every zero as unavailable. Revisit the rule if authoritative source documentation clarifies the meaning of these values.

## Repository layout

```text
price-pulse/
├── airflow/       # Airflow DAGs and Airflow image configuration
├── data/
│   ├── raw/       # Local timestamped source snapshots (ignored by Git)
│   └── processed/ # Generated CSVs and isolated replay outputs
├── docs/          # Project guide and snapshot replay documentation
├── scripts/       # Extraction, normalization, audit, cleaning, loading, replay
├── sql/           # Schema, analytics model, snapshot-history migrations, queries
├── tests/         # Automated tests
├── Dockerfile
├── requirements.txt
├── .env.example
└── README.md
```

Generated data, raw source snapshots, local environment files, virtual environments, and operational logs are intentionally excluded from Git. A fresh clone therefore needs to fetch a source snapshot before local replay can be performed.

## Run with Docker Compose

Docker Compose is the main reproducible route for running the database and orchestrated pipeline.

1. Create your local environment file and set private passwords. Do not commit `.env`:

   ```bash
   cp .env.example .env
   ```

2. Start PostgreSQL and Airflow:

   ```bash
   docker compose up -d --build db airflow
   docker compose ps
   ```

3. Run the current ingestion pipeline in the pipeline container:

   ```bash
   docker compose run --rm --build pipeline python scripts/run_pipeline.py
   ```

The PostgreSQL image runs initialization SQL files under `/docker-entrypoint-initdb.d/` only when its data directory is first initialized. If you already have an older database volume that predates snapshot history and replay auditing, apply the migrations explicitly from the repository root:

```bash
docker compose exec -T db psql -U postgres -d pricepulse -v ON_ERROR_STOP=1 < sql/008_create_snapshot_history.sql
docker compose exec -T db psql -U postgres -d pricepulse -v ON_ERROR_STOP=1 < sql/009_version_semantic_hash.sql
docker compose exec -T db psql -U postgres -d pricepulse -v ON_ERROR_STOP=1 < sql/010_create_snapshot_replay_runs.sql
```

Do not delete an existing PostgreSQL volume just to rerun initialization. Database initialization scripts and migrations are different: initialization runs on a new data directory, while existing databases need explicit migrations when they lack the newer tables or columns.

## Historical snapshot replay

Replay requires both a raw snapshot file available under `data/raw/` and its snapshot registered in the database. Raw files are not committed to Git, so use a snapshot that exists in your local working copy.

List local snapshots:

```bash
ls -1 data/raw/official_prices_*.json
```

Then pass the exact filename to the replay script:

```bash
docker compose run --rm --build pipeline \
  python scripts/replay_snapshot.py \
  --snapshot official_prices_YYYYMMDDTHHMMSSZ.json
```

Replace the example filename with an actual registered snapshot filename. Replay verifies the snapshot identity and recorded hashes/counts, normalizes, audits, cleans, runs tests, writes outputs under a unique directory beneath `data/processed/replays/`, and records the outcome in `audit.snapshot_replay_run`. A failed or unknown snapshot should be rejected and recorded as a failed replay; replay must not mutate live staging or analytics data.

Further details: [`docs/SNAPSHOT_REPLAY.md`](docs/SNAPSHOT_REPLAY.md).

## Airflow

Start the services with the Docker Compose commands above, then open the Airflow UI using the host and port configured in your Compose setup. Avoid placing passwords or other secrets in DAG code or committed files.

The scheduled `pricepulse_pipeline` DAG orchestrates current ingestion. The `pricepulse_snapshot_replay` DAG is for a deliberate replay of a chosen registered snapshot; provide the snapshot filename using the DAG's run configuration as described in [`docs/SNAPSHOT_REPLAY.md`](docs/SNAPSHOT_REPLAY.md).

## Local Python workflow

For individual transformation and audit work outside Docker, use a Python virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The exact local workflow depends on whether PostgreSQL is available locally and how its credentials are configured. The full pipeline requires a reachable database; do not hard-code credentials in source files.

Useful component commands from the repository root include:

```bash
python scripts/inspect_source.py
python scripts/normalize_source.py
python scripts/audit_data.py
python scripts/clean_prices.py
python -m pytest -q
```

The script names describe their current roles; consult the script help or project guide before assuming an individual command downloads, loads, or otherwise changes data.

## Tests and continuous integration

Run the automated suite with:

```bash
python -m pytest -q
```

The GitHub Actions workflow compiles Python source under `scripts/` and `tests/`, installs dependencies from `requirements.txt`, and runs the test suite on pushes and pull requests. A passing unit-test suite is useful evidence, but it does not by itself prove that every Docker, database, and Airflow integration path is production-ready.

## Important design decisions and limitations

- **Product identifiers stay strings.** Codes can contain leading zeroes and must not be converted to integers.
- **The analytics fact table is a current product-month view.** The loader upserts values into this table. Historical values associated with registered raw snapshots are tracked separately in the audit snapshot-observation tables, rather than represented as multiple versions of the same product-month in the analytics fact table.
- **Historical replay is isolated.** Replay results go to a separate output directory and replay-run audit record; they are not loaded into live analytics tables.
- **Zero handling is an assumption.** The six source zeros are flagged as unavailable for analysis, while their original values are retained.
- **Monthly comparisons need calendar alignment.** A `LAG(..., 12)` query assumes there is one row for every calendar month per product. For incomplete timelines, align by explicit dates rather than assuming twelve rows always equal twelve calendar months.
- **Production operations are not complete.** Broader integration tests, alerting, monitoring, deployment, and operational runbooks remain opportunities for further development.
- **Protect local data and credentials.** Never commit `.env`, passwords, database dumps, `.venv/`, generated data, or large raw snapshots. See [`docs/GIT_WORKFLOW.md`](docs/GIT_WORKFLOW.md).

## Documentation

- [Project guide](docs/PROJECT_GUIDE.md)
- [Historical snapshot replay](docs/SNAPSHOT_REPLAY.md)
- [Git workflow](docs/GIT_WORKFLOW.md)

## Learning approach

Each milestone should answer four questions: **What did we build? Why is it needed? How does it work? How do we know it behaves correctly?** The goal is not to accumulate technologies for their own sake, but to demonstrate a coherent, testable data system and explain its engineering trade-offs.
