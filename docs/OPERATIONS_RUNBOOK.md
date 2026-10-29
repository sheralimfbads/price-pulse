# PricePulse — Operations Runbook & Maintenance Guide

> **Companion Document:** [docs/LEARNING_HANDBOOK.md](LEARNING_HANDBOOK.md)
> This runbook is the definitive operational manual for running, testing, debugging, and maintaining the PricePulse data engineering platform in local development and production-like environments.

---

## Table of Contents

1. [Prerequisites & Environment Configuration](#1-prerequisites--environment-configuration)
2. [Starting & Stopping the System](#2-starting--stopping-the-system)
3. [Verified Service Endpoints](#3-verified-service-endpoints)
4. [Day-to-Day Operations & CLI Usage](#4-day-to-day-operations--cli-usage)
5. [Running the Ingestion Pipeline](#5-running-the-ingestion-pipeline)
6. [Historical Snapshot Replay Workflow](#6-historical-snapshot-replay-workflow)
7. [Database Migrations & Recovery](#7-database-migrations--recovery)
8. [Automated Testing & QA Verification](#8-automated-testing--qa-verification)
9. [Operational Troubleshooting Guide](#9-operational-troubleshooting-guide)

---

## 1. Prerequisites & Environment Configuration

### System Prerequisites
- **Operating System:** Linux, macOS, or Windows (WSL2 recommended).
- **Docker Engine:** Version 24+ with **Docker Compose v2+** (`docker compose` CLI).
- **Python:** Version 3.12+ (only required if running tests/scripts on the host outside Docker).
- **Git:** Version 2.40+.

### Environment File Setup (`.env`)
PricePulse uses an environment file (`.env`) to configure database credentials, ports, and operational settings.

```bash
# 1. Clone or navigate to the repository root
cd /path/to/price-pulse

# 2. Copy the template to create your local .env
cp .env.example .env
```

> [!CAUTION]
> **Data Security Rules:**
> - Never commit `.env` to Git. (It is listed in `.gitignore`.)
> - Never commit raw downloaded files in `data/raw/` or database backups in `backups/`.
> - Always use strong passwords in non-development environments.

### Host Ports vs. Container Ports
A common point of confusion for engineers is container port mapping. PricePulse configures ports to prevent collisions with any existing local PostgreSQL installations on your machine:

| Service | Internal Container Port | Forwarded Host Port | Why Different? |
|---|---|---|---|
| **PostgreSQL (`db`)** | `5432` | **`5434`** | Avoids colliding with default local PostgreSQL instances running on port `5432`. |
| **FastAPI Backend (`api`)** | `8000` | **`8000`** | Standard web application development port. |
| **Airflow 3 (`airflow`)** | `8080` | **`8080`** | Standard Airflow webserver UI port. |

- When connecting from your **laptop terminal (host)**: Use `DB_HOST=127.0.0.1` and `DB_PORT=5434`.
- When connecting from **inside a container (Docker network)**: Use `DB_HOST=db` and `DB_PORT=5432`.

---

## 2. Starting & Stopping the System

### Primary Startup Command
To build images, initialize the network, run database migrations, and start all services in the background:

```bash
docker compose up -d --build
```

### Verifying Service Health
Check the runtime status of all containers:

```bash
docker compose ps
```

**Expected Healthy State:**
```text
NAME                    IMAGE                 SERVICE   STATUS                        PORTS
price-pulse-db-1        postgres:16           db        Up (healthy)                  127.0.0.1:5434->5432/tcp
price-pulse-migrate-1   price-pulse-migrate   migrate   Exited (0)
price-pulse-api-1       price-pulse-api       api       Up (healthy)                  127.0.0.1:8000->8000/tcp
price-pulse-airflow-1   price-pulse-airflow   airflow   Up                            127.0.0.1:8080->8080/tcp
```
*(Note: `price-pulse-migrate-1` executes DDL migrations and gracefully exits with status `0`. This is expected behavior!)*

### Safe Shutdown (Preserving Data)
To stop all containers safely:

```bash
docker compose down
```
> [!NOTE]
> All PostgreSQL data remains safely preserved inside the Docker named volume `pricepulse_db_data`. When you start the stack again, all tables and records will be intact.

> [!WARNING]
> **DO NOT USE `docker compose down -v`!**
> The `-v` flag deletes all Docker volumes, which permanently destroys your local database and requires running the entire ingestion pipeline and migrations from scratch.

---

## 3. Verified Service Endpoints

Once the stack is running, access these verified local endpoints:

| Application / Service | URL | Purpose |
|---|---|---|
| **PricePulse Dashboard** | [http://localhost:8000/](http://localhost:8000/) | Responsive commodity intelligence UI, interactive SVG charts, top movers. |
| **Interactive OpenAPI Documentation** | [http://localhost:8000/docs](http://localhost:8000/docs) | Swagger UI for exploring and testing REST API endpoints interactively. |
| **Database Readiness Probe** | [http://localhost:8000/health/ready](http://localhost:8000/health/ready) | Verifies database connectivity and existence of analytics views (`{"status":"ok","database":"ready"}`). |
| **Service Liveness Probe** | [http://localhost:8000/health/live](http://localhost:8000/health/live) | Lightweight container liveness check (`{"status":"ok"}`). |
| **Airflow 3 Web UI** | [http://localhost:8080/](http://localhost:8080/) | Workflow orchestrator UI for inspecting DAGs, task runs, and logs. |

---

## 4. Day-to-Day Operations & CLI Usage

### 1. Interacting with the REST API
You can query the API using `curl` or any HTTP client:

```bash
# Get overall dataset summary (total products, observation count, latest month)
curl -s http://127.0.0.1:8000/api/v1/overview | jq

# Search commodities by keyword (e.g., "beef")
curl -s "http://127.0.0.1:8000/api/v1/products?q=beef" | jq

# Get historical price time-series for Rice (code 001)
curl -s "http://127.0.0.1:8000/api/v1/products/001/prices?limit=5" | jq

# Get top YoY price movers for the latest month
curl -s "http://127.0.0.1:8000/api/v1/analytics/latest-movers?limit=3" | jq
```

### 2. Inspecting the Database with `psql`
You can open an interactive PostgreSQL shell inside the container without installing `psql` on your laptop:

```bash
docker compose exec db psql -U postgres -d pricepulse
```

Or run one-off SQL commands with formatted output:
```bash
docker compose exec db psql -U postgres -d pricepulse -P pager=off -c "
SELECT p.product_code, p.product_name_en, f.period, f.average_price_uzs_per_kg
FROM analytics.fact_monthly_official_price f
JOIN analytics.dim_product p ON p.product_key = f.product_key
WHERE p.product_code = '001'
ORDER BY f.period DESC LIMIT 3;
"
```

### 3. Tailing Service Logs
To view live logs from running services:

```bash
# View live API logs (HTTP requests and exceptions)
docker compose logs -f api

# View live Airflow logs
docker compose logs -f airflow

# View PostgreSQL database server logs
docker compose logs -f db
```

---

## 5. Running the Ingestion Pipeline

PricePulse supports two methods of executing the end-to-end ingestion pipeline:

### Method A: Standalone Sequential Local Run (Recommended for Dev)
Execute the complete pipeline sequentially using Docker Compose:

```bash
docker compose run --rm pipeline python scripts/run_pipeline.py
```

**Pipeline Execution Stages:**
1. `extract_source.py`: Fetches raw JSON from the SIAT API and writes `data/raw/official_prices_*.json`.
2. `load_snapshot_history.py`: Computes raw and semantic SHA-256 hashes and registers the file in `audit.source_snapshot`.
3. `normalize_source.py`: Melts wide JSON into `data/processed/official_prices_long.csv`.
4. `audit_data.py`: Validates schema, uniqueness, date formats, and exit code.
5. `clean_prices.py`: Maps zero prices to `zero_marked_unavailable` and outputs `data/processed/official_prices_analytics.csv`.
6. `load_to_postgres.py`: Executes an ACID transaction loading staging and star schema tables.

### Method B: Orchestrated Run via Apache Airflow 3
1. Open the Airflow UI at [http://localhost:8080/](http://localhost:8080/).
2. Locate the DAG: **`pricepulse_pipeline`**.
3. Toggle the DAG switch to **Active**.
4. Click the **Trigger DAG** button (Play icon) on the right.
5. Click into the Grid/Graph view to monitor individual task execution and view logs.

---

## 6. Historical Snapshot Replay Workflow

Historical snapshot replay allows you to verify that an earlier source file can be reprocessed under current analytical rules without modifying production database records.

### Step 1: List Available Snapshots in PostgreSQL
```bash
docker compose exec db psql -U postgres -d pricepulse -P pager=off -c "
SELECT snapshot_filename, fetched_at_utc, observation_count, LEFT(raw_sha256, 12) || '...' AS raw_hash
FROM audit.source_snapshot
ORDER BY fetched_at_utc DESC;
"
```

### Step 2: Run the Replay CLI
Run `replay_snapshot.py` with the selected snapshot:

```bash
docker compose run --rm pipeline python scripts/replay_snapshot.py \
  --snapshot official_prices_20261026T042335Z.json \
  --trigger-source cli
```

### Step 3: Verify Replay Execution
The script normalizes, audits, cleans, and runs unit tests in an isolated sandbox folder. Verify that the run succeeded by querying the audit ledger:

```bash
docker compose exec db psql -U postgres -d pricepulse -P pager=off -c "
SELECT
    requested_snapshot_filename,
    status,
    normalized_row_count,
    analytics_row_count,
    output_directory,
    finished_at_utc
FROM audit.snapshot_replay_run
ORDER BY started_at_utc DESC
LIMIT 1;
"
```
**Safety Invariant:** The replay engine produces files inside `data/processed/replays/<snapshot>/<uuid>/` and logs to `audit.snapshot_replay_run`. **It never alters staging or fact tables.**

---

## 7. Database Migrations & Recovery

### How Migrations Work
PricePulse executes migrations automatically via `scripts/migrate.py`:
- Migrations live in `sql/` prefixed by order (e.g., `001_create_schema.sql`, `011_create_analytics_views.sql`).
- When run, `scripts/migrate.py` calculates the SHA-256 checksum of each file.
- It consults `audit.schema_migration`:
  - **DDL Tables:** Executed once. If the checksum has already been applied, it is safely skipped.
  - **Repeatable Views:** Scripts `011` and `012` use `CREATE OR REPLACE VIEW`. They re-apply whenever modified.

### Manually Running Migrations
To manually apply migrations at any time:

```bash
docker compose run --rm migrate
```

### Inspecting Migration History
```bash
docker compose exec db psql -U postgres -d pricepulse -P pager=off -c "
SELECT filename, LEFT(checksum, 16) || '...' AS checksum, applied_at_utc
FROM audit.schema_migration
ORDER BY filename;
"
```

### Recovery from a Failed Migration
If a migration fails due to a SQL syntax error:
1. Fix the error in the corresponding `sql/*.sql` file.
2. Do **NOT** delete the database volume.
3. Re-run `docker compose run --rm migrate`. Because migrations are wrapped in transactions, failed files do not leave half-applied tables behind.

---

## 8. Automated Testing & QA Verification

PricePulse contains a comprehensive 64-test automated suite.

### 1. Running Host Tests (52 Tests)
Run unit, mock, and live database tests on your development machine:

```bash
# Activate virtual environment
source .venv/bin/activate

# Run full host suite
python -m pytest -v
```
*(Expected: 52 passed, 12 skipped for Airflow container).*

To run against the live local database on port `5434`:
```bash
DB_PORT=5434 python -m pytest tests/test_api.py -v
```

### 2. Running Airflow 3 DAG Tests (12 Tests)
Run Airflow DAG validation tests inside the running Airflow container:

```bash
docker compose exec airflow pytest /opt/pricepulse/tests/test_dags.py -v -p no:cacheprovider
```
*(Validates DAG parsing, absence of import cycles, monthly schedules, retries, and task dependencies).*

### 3. Continuous Integration (GitHub Actions)
PricePulse executes `.github/workflows/ci.yml` on every Git push:
- Validates Python syntax.
- Boots an ephemeral PostgreSQL 16 service.
- Applies all migrations via `scripts/migrate.py`.
- Runs the test suite against the ephemeral database.
- Validates Docker Compose configuration (`docker compose config --quiet`).

---

## 9. Operational Troubleshooting Guide

| # | Symptom | Possible Root Cause | Safe Diagnostic | Recommended Fix |
|---|---|---|---|---|
| 1 | **PostgreSQL container is unhealthy or restarting** | Port collision or corrupt shared memory. | `docker compose logs db` | Check if another PostgreSQL instance is using port `5434`. Stop conflicting service: `sudo systemctl stop postgresql`. |
| 2 | **API returns 503 "Required analytics objects are not available"** | Migrations have not completed, or analytical views are missing. | `curl -s http://localhost:8000/health/ready` | Run migration service: `docker compose run --rm migrate`. Verify views exist with `\dv analytics.*`. |
| 3 | **Host tests fail with "Connection refused on port 5432"** | Host scripts attempting to connect to internal container port. | Check `DB_PORT` in your host environment. | Set `DB_PORT=5434` in your host environment or `.env`. Remember container port is `5432`, host port is `5434`. |
| 4 | **Ingestion fails with "Duplicate key violates unique constraint"** | Raw data contains duplicate `(product_code, period)` observations. | Run `audit_data.py` on the long CSV. | The loader uses `ON CONFLICT (product_code, period) DO UPDATE`. If failing before load, inspect upstream source for corrupt duplicate keys. |
| 5 | **Airflow web UI is inaccessible on port 8080** | Airflow container still initializing or database locked. | `docker compose logs airflow` | Airflow 3 standalone takes ~15-20 seconds to boot the first time. Check logs for initialization completion. |
| 6 | **Snapshot replay fails with "Snapshot not registered"** | Requested snapshot filename does not exist in `audit.source_snapshot`. | Query `audit.source_snapshot` for filename. | Run `scripts/load_snapshot_history.py` first to compute hashes and register the raw snapshot. |
| 7 | **Browser dashboard shows empty chart or network error** | Web API container is down or CORS header blocked. | Inspect browser DevTools Console & Network tabs. | Check API container health: `docker compose ps api`. Verify API logs: `docker compose logs api`. |
| 8 | **`psycopg.errors.IndeterminateDatatype` during SQL execution** | Query parameter used in `IS NULL` check without explicit SQL type cast. | Check stack trace in API logs. | Use explicit PostgreSQL type casts in SQL: `%(code)s::text IS NULL` instead of `%(code)s IS NULL`. |
| 9 | **Database migration fails with "password authentication failed"** | Passwords in `.env` do not match the initialized PostgreSQL volume. | Check `POSTGRES_PASSWORD` in `.env`. | Ensure `.env` credentials match those used when `pricepulse_db_data` was first created. Never overwrite `.env` with dummy values. |
| 10 | **Git shows unexpected modified files in `data/`** | Temporary processing artifacts created outside `.gitignore`. | Run `git status`. | Check `.gitignore`. Ensure `data/raw/` and `data/processed/` are properly ignored. Never commit raw datasets. |
