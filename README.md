# PricePulse — Uzbekistan Commodity Price Analytics Platform

PricePulse is an end-to-end data engineering platform and analytical application built on official monthly average commodity prices from the National Statistics Committee of Uzbekistan.

The system demonstrates the entire modern data lifecycle:

$$\text{Source API} \longrightarrow \text{Ingestion} \longrightarrow \text{Snapshot Lineage} \longrightarrow \text{Auditing} \longrightarrow \text{Cleaning} \longrightarrow \text{PostgreSQL Star Schema} \longrightarrow \text{Analytical SQL Views} \longrightarrow \text{FastAPI Backend} \longrightarrow \text{Interactive Dashboard}$$

All components are containerized, reproducible, orchestrated via Apache Airflow 3, backed by transactional database migrations, and covered by automated unit, integration, and end-to-end test suites.

---

## 1. Product Capabilities

- **Automated Ingestion Pipeline:** Fetches official statistics JSON payloads with exponential-backoff retries, explicit timeouts, response structure validation, and atomic writes to local snapshot storage.
- **Cryptographic Lineage & Snapshot Tracking:** Computes both physical file SHA-256 and canonicalized logical semantic SHA-256 (v2) hashes to guarantee snapshot uniqueness and dataset integrity in `audit.source_snapshot`.
- **Deterministic Historical Snapshot Replay:** Enables historical audits by reproducing normalized and analytical datasets in isolated directories (`data/processed/replays/...`) without mutating live production tables.
- **Dimensional Analytics Model:** Enforces a star schema (`analytics.dim_product`, `analytics.dim_month`, `analytics.fact_monthly_official_price`) with transactional loads, constraint checks, and foreign-key integrity.
- **Calendar-Based Analytics Views:** Precomputes month-over-month (MoM) and year-over-year (YoY) price trends using calendar interval joins rather than naive row-position lags. Ranks YoY percentage changes deterministically.
- **FastAPI Read-Only Backend:** Exposes typed, OpenAPI-documented REST endpoints with pagination, query validation, and least-privilege database role isolation (`pricepulse_api`).
- **Interactive Browser Dashboard:** Provides an accessible UI with summary metrics, top market movers, product exploration, and pure SVG time-series charts with honest gap handling for unavailable months.
- **Orchestration:** Managed by Apache Airflow 3 (`pricepulse_pipeline` and `pricepulse_snapshot_replay`).

---

## 2. Upstream Data Source & Semantics

- **Source API:** [Uzbekistan Statistics Agency SIAT JSON Endpoint](https://api.siat.stat.uz/media/uploads/sdmx/sdmx_data_1308.json)
- **Dataset:** *Dynamics of average prices of selected goods in markets and stores*
- **Measurement Unit:** Uzbek Soums (UZS) per kilogram
- **Frequency:** Monthly (January 2021 through September 2026 in verified baseline)
- **Coverage:** 41 products across 69 calendar months (2,829 product-month observations)

### Core Semantic Rules

1. **Product Code Fidelity:** Product identifiers such as `001`, `0004`, `0050`, and `0070` are treated as alphanumeric strings. Leading zeros are strictly preserved across all ingestion, database, and API layers.
2. **Calendar Continuity:** Monthly comparisons join on calendar dates (`month_start - INTERVAL '1 year'`), ensuring timeline gaps never cause misleading comparisons across non-adjacent periods.
3. **Source-Zero Assumption:** Exactly 6 records in the inspected dataset report a price of `0.00` (seasonal summer fruits such as watermelon and melon in early spring). The pipeline preserves original source values in `source_price_uzs_per_kg`, sets the analytical price to `NULL`, and assigns `price_status = 'zero_marked_unavailable'`. This is a documented **project assumption**, not an unverified assertion about the publisher's internal encoding. Missing prices are never silently coerced to zero or artificially imputed.

---

## 3. Architecture & Data Flow

```text
[ SIAT Stat UZ JSON API ]
            │
            ▼ (HTTP GET with retry & timeouts)
  [ data/raw/official_prices_*.json ]
            │
            ├─────────────────────────────────────────┐
            ▼                                         ▼
  [ scripts/normalize_source.py ]        [ scripts/load_snapshot_history.py ]
            │                                         │
            ▼                                         ▼
  [ data/processed/official_prices_long.csv ]  [ audit.source_snapshot ]
            │
            ▼
  [ scripts/audit_data.py ]
            │
            ▼
  [ scripts/clean_prices.py ]
            │
            ▼
  [ data/processed/official_prices_analytics.csv ]
            │
            ▼
  [ scripts/load_to_postgres.py ]
            │
   ┌────────┴────────────────────────────────────────┐
   ▼                                                 ▼
[ staging.official_price_observations ]   [ analytics star schema ]
                                          - dim_product
                                          - dim_month
                                          - fact_monthly_official_price
                                                     │
                                                     ▼
                                          [ PostgreSQL analytics views ]
                                          - vw_monthly_price_changes
                                          - vw_year_over_year_price_changes
                                          - vw_yoy_price_change_rankings
                                                     │
                                                     ▼
                                          [ FastAPI Service (app.main) ]
                                                     │
                                                     ▼
                                          [ Web Dashboard (HTML/JS/SVG) ]
```

---

## 4. Quickstart: 1-Command Developer Environment

### Prerequisites
- Docker & Docker Compose v2+
- Python 3.12+ (optional, for local host development outside Docker)

### 1. Configure Environment
```bash
cp .env.example .env
```
*(The defaults in `.env.example` are pre-wired for local development.)*

### 2. Start Services via Docker Compose
```bash
docker compose up -d --build
```
This automatically initializes:
- `db`: PostgreSQL 16 (healthy on `127.0.0.1:5434`, internal port `5432`).
- `migrate`: One-off migration runner applying schema and permissions, then gracefully exiting (`0`).
- `api`: FastAPI application (healthy on `http://127.0.0.1:8000`).
- `airflow`: Apache Airflow 3 standalone scheduler/webserver on `http://127.0.0.1:8080`.

### 3. Access the Applications
- **PricePulse Dashboard:** [http://localhost:8000/](http://localhost:8000/)
- **Interactive API Documentation:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Airflow Web UI:** [http://localhost:8080/](http://localhost:8080/)

### 4. Stop Services
```bash
docker compose down
```
*(Persistent data remains safely stored in the `pricepulse_db_data` Docker volume.)*

---

## 5. Repository Layout

```text
price-pulse/
├── airflow/
│   ├── dags/
│   │   ├── pricepulse_pipeline.py         # Monthly ingestion DAG (Airflow 3)
│   │   └── pricepulse_snapshot_replay.py  # Historical replay DAG
│   └── Dockerfile                         # Airflow 3 custom runtime image
├── app/
│   ├── config.py                          # Pydantic/dataclass environment configuration
│   ├── db.py                              # Psycopg 3 connection factory
│   ├── main.py                            # FastAPI application entry point
│   ├── queries.py                         # Parameterized SQL statements
│   ├── schemas.py                         # Typed response schemas (Pydantic v2)
│   ├── static/                            # CSS styles and vanilla JS client
│   └── templates/                         # Jinja2 dashboard templates
├── data/
│   ├── raw/                               # Raw JSON source snapshots (gitignored)
│   └── processed/                         # Processed long & analytical CSVs (gitignored)
├── docker/
│   └── postgres/init/                     # Initialization scripts for fresh containers
├── docs/
│   ├── DATA_MODEL.md                      # Star schema & data dictionary reference
│   ├── DECISIONS_AND_LIMITATIONS.md       # Architecture Decision Records (ADRs)
│   ├── GIT_WORKFLOW.md                    # Git conventions & ignore rules
│   ├── OPERATIONS_AND_API_GUIDE.md        # Comprehensive operations runbook
│   ├── PROJECT_GUIDE.md                   # Pedagogical overview and design notes
│   └── SNAPSHOT_REPLAY.md                 # Deep-dive on snapshot reproducibility
├── scripts/
│   ├── audit_data.py                      # Pandas dataset validation and quality gates
│   ├── clean_prices.py                    # Analytical pricing transformation rules
│   ├── extract_source.py                  # HTTP client with retries & atomic write
│   ├── inspect_source.py                  # Diagnostic source JSON reader
│   ├── load_snapshot_history.py           # Snapshot registration & semantic hashing
│   ├── load_to_postgres.py                # Transactional staging & star schema loader
│   ├── migrate.py                         # Idempotent SHA-256 migration runner
│   ├── normalize_source.py                # Wide-to-long dataset transformation
│   ├── replay_snapshot.py                 # Isolated historical snapshot replay engine
│   └── run_pipeline.py                    # Standalone sequential local pipeline runner
├── sql/
│   ├── 001_create_schema.sql              # Staging table DDL
│   ├── 005_create_analytics_model.sql     # Dimension and fact tables DDL
│   ├── 008_create_snapshot_history.sql    # Snapshot registry tables DDL
│   ├── 009_version_semantic_hash.sql      # Semantic hash versioning migration
│   ├── 010_create_snapshot_replay_runs.sql# Replay audit run logs DDL
│   ├── 011_create_analytics_views.sql     # MoM and YoY price change views
│   ├── 012_price_change_rankings.sql      # YoY price percentage ranking view
│   └── 013_schema_migrations.sql          # Migration tracking table DDL
├── tests/
│   ├── test_api.py                        # FastAPI unit, mock, and live database e2e tests
│   ├── test_clean_prices.py               # Price cleaning and status assignment unit tests
│   ├── test_dags.py                       # Airflow 3 DAG validation tests
│   ├── test_replay_snapshot.py            # Snapshot validation, hashing, and replay tests
│   └── test_run_pipeline.py               # Sequential runner process execution tests
├── compose.yaml                           # Multi-service Compose specification
├── Dockerfile                             # Container image for API, migrations, and pipeline
├── pytest.ini                             # Pytest configuration and marker definitions
└── requirements.txt                       # Explicitly pinned application dependencies
```

---

## 6. Database Migrations & Security

Migrations are automated via `scripts/migrate.py` and tracked in `audit.schema_migration`:
- **One-Time Migrations:** DDL statements executed once per file SHA-256 checksum.
- **Repeatable Migrations:** Analytical views re-applied idempotently (`CREATE OR REPLACE VIEW`).

### Least-Privilege Security Roles
- `pricepulse_dev`: Assigned to ingestion pipeline and historical replay. Holds full `SELECT`, `INSERT`, `UPDATE`, `DELETE` access to `staging`, `analytics`, and `audit`.
- `pricepulse_api`: Assigned to FastAPI web backend. Holds read-only `SELECT` access strictly on `analytics.*` and `audit.source_snapshot`. Access to `staging` is explicitly revoked.

---

## 7. REST API & Endpoints

The API is served at `http://127.0.0.1:8000`. All analytical computations are executed directly inside PostgreSQL views.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Web dashboard |
| `GET` | `/docs` | Interactive OpenAPI / Swagger UI |
| `GET` | `/health/live` | Liveness probe (`{"status": "ok"}`) |
| `GET` | `/health/ready` | Readiness probe verifying DB connectivity and views |
| `GET` | `/api/v1/overview` | Dataset counts, latest month, latest source snapshot |
| `GET` | `/api/v1/products` | Paginated product list with search (`?q=beef&limit=10`) |
| `GET` | `/api/v1/products/{code}/prices` | Monthly price history with calendar MoM changes |
| `GET` | `/api/v1/analytics/latest-movers` | Ranked top YoY price percentage increases/decreases |

---

## 8. Historical Snapshot Replay

To verify reproducibility without modifying live tables:

```bash
docker compose run --rm pipeline \
  python scripts/replay_snapshot.py \
  --snapshot official_prices_20261020T105154Z.json \
  --trigger-source cli
```

Replay behavior:
1. Validates snapshot registration and cryptographic hashes in PostgreSQL.
2. Normalizes, audits, and cleans data into a unique run directory: `data/processed/replays/<snapshot>/<run_uuid>/`.
3. Runs the unit test suite against the replayed dataset.
4. Records execution status, output hashes, and row counts in `audit.snapshot_replay_run`.
5. **Never mutates live staging or fact tables.**

---

## 9. Testing & Quality Assurance

The repository includes a comprehensive 62-test automated suite:

### Run Local Unit, Mock, and Live Database E2E Tests
```bash
source .venv/bin/activate
set -a && source .env && set +a
pytest -v
```
*(Executes 50 tests: 31 API unit/integration/e2e tests, 11 snapshot replay tests, 5 cleaning tests, and 2 pipeline tests).*

### Run Airflow 3 Container DAG Tests
```bash
docker compose exec airflow pytest /opt/pricepulse/tests/test_dags.py -v -p no:cacheprovider
```
*(Executes 12 tests validating Airflow 3 DAG imports, schedules, task dependencies, retries, and configuration).*

### Continuous Integration (GitHub Actions)
The workflow in `.github/workflows/ci.yml`:
- Compiles Python code across `scripts/`, `tests/`, and `app/`.
- Provisions an ephemeral PostgreSQL 16 service container.
- Executes `scripts/migrate.py` to test fresh database setup.
- Runs the complete unit and e2e test suite.
- Validates Docker Compose configuration (`docker compose config --quiet`).

---

## 10. Engineering Decisions & Invariants

1. **Analytical SQL vs. Application Logic:** All window functions, percentage calculations, rankings, and calendar intervals reside in PostgreSQL views (`sql/011_create_analytics_views.sql`, `sql/012_price_change_rankings.sql`). The API and dashboard never duplicate analytical formulas.
2. **Honest Time-Series Visualization:** The SVG chart draws continuous lines only across consecutive available observations. Gaps indicate missing or unavailable prices, preventing false interpolation.
3. **No Unjustified Technologies:** The project explicitly relies on lightweight, robust tools (PostgreSQL, Python, FastAPI, Airflow 3, Docker Compose) rather than introducing unnecessary distributed systems (Spark, Kafka, Kubernetes) for a homogeneous dataset.

For detailed Architecture Decision Records, see [docs/DECISIONS_AND_LIMITATIONS.md](docs/DECISIONS_AND_LIMITATIONS.md) and the operational guide in [docs/OPERATIONS_AND_API_GUIDE.md](docs/OPERATIONS_AND_API_GUIDE.md).
