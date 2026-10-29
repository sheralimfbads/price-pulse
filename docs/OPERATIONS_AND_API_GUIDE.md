# PricePulse Operations and API Guide

## 1. System Architecture

PricePulse implements an end-to-end data engineering lifecycle:

```
[Official Statistics API: sdmx_data_1308.json]
                        │
                        ▼ (HTTP GET with retry & timeouts)
             [data/raw/official_prices_*.json]
                        │
                        ├──────────────────────────┐
                        ▼                          ▼
              [scripts/normalize_source.py]   [scripts/load_snapshot_history.py]
                        │                          │
                        ▼                          ▼
        [data/processed/official_prices_long.csv]  [audit.source_snapshot]
                        │
                        ▼
              [scripts/audit_data.py]
                        │
                        ▼
              [scripts/clean_prices.py]
                        │
                        ▼
    [data/processed/official_prices_analytics.csv]
                        │
                        ▼
            [scripts/load_to_postgres.py]
                        │
       ┌────────────────┴────────────────┐
       ▼                                 ▼
[staging.official_price_observations]  [analytics star schema]
                                       - dim_product
                                       - dim_month
                                       - fact_monthly_official_price
                                                 │
                                                 ▼
                                       [analytics SQL views]
                                       - vw_monthly_price_changes
                                       - vw_year_over_year_price_changes
                                       - vw_yoy_price_change_rankings
                                                 │
                                                 ▼
                                        [FastAPI Application]
                                        (app.main:app, read-only)
                                                 │
                                                 ▼
                                        [Browser Dashboard]
                                        (overview, movers, time-series)
```

## 2. Quickstart: Running the Complete System

### Prerequisites
- Docker & Docker Compose
- Python 3.12+ (for local host development)

### Environment Configuration
Copy `.env.example` to `.env` and set local passwords:
```bash
cp .env.example .env
# Edit .env: set POSTGRES_ADMIN_PASSWORD, DB_PASSWORD, API_DB_PASSWORD
```

### Start Services via Docker Compose
```bash
docker compose up -d --build
```
This starts:
- `db`: PostgreSQL 16 on `127.0.0.1:5434` (internal port `5432`).
- `migrate`: One-off migration runner applying schema and permissions, then exiting (0).
- `api`: FastAPI service on `http://127.0.0.1:8000` (healthy readiness check).
- `airflow`: Apache Airflow 3 standalone on `http://127.0.0.1:8080`.

### Stop Services
```bash
docker compose down
```
*Note: The named volume `pricepulse_db_data` is preserved.*

---

## 3. Database Migrations and Roles

Migrations are managed by `scripts/migrate.py` and tracked in `audit.schema_migration`:
- **Once migrations**: DDL scripts executed once per unique file SHA-256 (`001_create_schema.sql`, `005_create_analytics_model.sql`, etc.).
- **Repeatable migrations**: Analytical views (`011_create_analytics_views.sql`, `012_price_change_rankings.sql`) applied idempotently with `CREATE OR REPLACE VIEW`.

### Role Privileges
- `pricepulse_dev`: Read/write access on `staging`, `analytics`, and `audit` schemas.
- `pricepulse_api`: Read-only (`SELECT`) on `analytics.*` and `audit.source_snapshot`. No staging schema access.

Run migrations manually if needed:
```bash
python scripts/migrate.py
```

---

## 4. API Endpoints

The API is strictly read-only and served on `http://127.0.0.1:8000`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Web dashboard |
| `GET` | `/docs` | OpenAPI / Swagger interactive documentation |
| `GET` | `/health/live` | Liveness probe: returns `{"status": "ok"}` |
| `GET` | `/health/ready` | Readiness probe: verifies DB connectivity and analytical views |
| `GET` | `/api/v1/overview` | Dataset summary: observation counts, month range/count, and snapshot currently loaded into analytics |
| `GET` | `/api/v1/products` | Paginated product list with search (`?q=`, `?limit=`, `?offset=`) |
| `GET` | `/api/v1/products/{code}/prices` | Monthly price history with calendar month-over-month changes |
| `GET` | `/api/v1/analytics/latest-movers` | Top YoY percentage price increases and decreases for latest month |

---

## 5. Airflow Orchestration

Airflow 3 operates in standalone mode:
- **`pricepulse_pipeline`**: Scheduled monthly (`0 6 20 * *`) to extract official data, register snapshot history, normalize, audit, clean, and reconcile the latest snapshot to PostgreSQL. Unit and integration tests run in CI rather than as part of routine ingestion.
- **`pricepulse_snapshot_replay`**: Manual DAG triggered with a JSON configuration:
  ```json
  {"snapshot_filename": "official_prices_20261020T105154Z.json"}
  ```
  Runs an isolated replay without altering live staging or analytics tables, and audits the result in `audit.snapshot_replay_run`.

---

## 6. Testing

### Run All Host Unit and API Tests
```bash
source .venv/bin/activate
pytest -v
```

### Run Real PostgreSQL E2E Tests
```bash
set -a && source .env && set +a
pytest -m e2e -v
```

The loader reconciliation integration test runs only when `PRICEPULSE_TEST_DB_NAME` points to a dedicated disposable database that has been migrated. It truncates its tables to verify snapshot replacement, so never point it at a development or production database. CI creates and migrates this database automatically.

### Run Airflow DAG Structure Tests Inside Container
```bash
docker compose exec airflow pytest /opt/pricepulse/tests/test_dags.py -v -p no:cacheprovider
```

### Run Complete Pipeline Locally
```bash
python scripts/run_pipeline.py
```
