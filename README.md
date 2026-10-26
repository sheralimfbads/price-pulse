# PricePulse Uzbekistan

A learning-focused data engineering project that builds a reproducible pipeline around official monthly average prices for selected goods in Uzbekistan.

PricePulse currently downloads a source JSON snapshot, normalizes its wide monthly data into a long-format CSV, audits and cleans the data, loads it into PostgreSQL, and models it for analytics using a small star schema.

> **Project status:** The local Python + SQL pipeline and PostgreSQL model are working. This is an educational portfolio project, not yet a production service. Docker, Airflow, dbt, cloud deployment, and historical source-revision tracking are future milestones.

## Why this project exists

Rather than building many disconnected tutorials, PricePulse grows one system step by step. Each new technology should solve a real limitation of the current version and be accompanied by tests and documentation.

## Data source

- Dataset: *Dynamics of average prices of some goods in markets and stores*.
- Publisher: National Statistics Committee of the Republic of Uzbekistan.
- Unit reported by the source: soums per kilogram.
- Frequency: monthly.
- Source endpoint: <https://api.siat.stat.uz/media/uploads/sdmx/sdmx_data_1308.json>
- Statistics portal: <https://stat.uz/en/official-statistics/prices-and-indexes>

The inspected source snapshot contained 41 product records and 69 months, from January 2021 through September 2026. The source's metadata includes duplicated publication/code fields with differing last-modified values; preserve and inspect source metadata rather than assuming every metadata entry is unique or consistent.

## Current pipeline

Run the pipeline from the repository root, with the virtual environment activated:

```bash
source .venv/bin/activate
python scripts/run_pipeline.py
```

The runner executes these stages in order:

1. **Extract / inspect source** — retrieve the source and preserve a timestamped raw JSON snapshot. In the original implementation, `inspect_source.py` performed both download and inspection; a refactor may separate these into `extract_source.py` and a diagnostic-only `inspect_source.py`.
2. **Normalize** — convert monthly columns into one row per product and month.
3. **Audit** — validate dates, product identifiers, duplicate keys, price values, and timeline coverage.
4. **Clean** — preserve source prices and create analytical prices plus an explicit `price_status`.
5. **Test** — run `pytest`.
6. **Load** — use Psycopg 3 to bulk-load CSV data into PostgreSQL and upsert staging and analytics tables in one transaction.

The loader prompts for the database password with `getpass`; credentials should not be hard-coded in Python or committed to Git.

## Current observed data counts

| Check | Expected / observed value |
|---|---:|
| Product records | 41 |
| Monthly periods | 69 |
| Normalized product-month rows | 2,829 |
| `analytics.dim_product` | 41 |
| `analytics.dim_month` | 69 |
| `analytics.fact_monthly_official_price` | 2,829 |
| Observed positive prices | 2,823 |
| Zero-marked unavailable prices | 6 |
| Duplicate product-month keys | 0 |

The six zeros came from the source JSON and were preserved by normalization. The current analytical rule maps these zeros to missing analytical prices while preserving the original values and marking them `zero_marked_unavailable`. This is an explicit project assumption based on the source's seasonal note, not a formally verified source encoding rule.

## Repository layout

```text
price-pulse/
├── data/
│   ├── raw/                 # Local timestamped source snapshots (ignored by Git)
│   └── processed/           # Generated normalized and analytical CSVs
├── docs/                    # Project and design documentation
├── scripts/
│   ├── inspect_source.py
│   ├── normalize_source.py
│   ├── audit_data.py
│   ├── clean_prices.py
│   ├── investigate_zero_prices.py
│   ├── load_to_postgres.py
│   └── run_pipeline.py
├── sql/
│   ├── 001_create_schema.sql
│   ├── 002_analytical_queries.sql
│   ├── 003_query_plans.sql
│   ├── 004_modeling_precheck.sql
│   ├── 005_create_analytics_model.sql
│   ├── 006_load_analytics_model.sql
│   └── 007_verify_analytics_model.sql
├── tests/
├── requirements.txt
└── .gitignore
```

This is the intended layout; file names may differ slightly if the extraction/inspection refactor is still in progress.

## Local setup

The project was developed on Ubuntu with Python in a virtual environment and PostgreSQL 16. Your local versions may differ.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install requests pandas pytest "psycopg[binary]"
python -m pip freeze > requirements.txt
```

Create the local PostgreSQL role and database once, if they do not already exist:

```bash
sudo -u postgres psql
```

Inside `psql`:

```sql
CREATE ROLE pricepulse_dev LOGIN;
\password pricepulse_dev
CREATE DATABASE pricepulse OWNER pricepulse_dev;
\q
```

Apply the SQL files in order when setting up an empty database:

```bash
psql -h localhost -U pricepulse_dev -d pricepulse -v ON_ERROR_STOP=1 -f sql/001_create_schema.sql
psql -h localhost -U pricepulse_dev -d pricepulse -v ON_ERROR_STOP=1 -f sql/005_create_analytics_model.sql
```

The numbered files `002`–`004` and `007` contain analytical queries, query-plan experiments, prechecks, and verification. `006` populates the model from staging, after the normalized/cleaned data has been imported or the Python loader is used. Follow the steps in [`docs/PROJECT_GUIDE.md`](docs/PROJECT_GUIDE.md) for the whole workflow.

## Useful commands

```bash
# Inspect the newest local source snapshot
python scripts/inspect_source.py

# Run component scripts individually
python scripts/normalize_source.py
python scripts/audit_data.py
python scripts/clean_prices.py
python -m pytest -q
python scripts/load_to_postgres.py

# Run the complete local pipeline
python scripts/run_pipeline.py

# Check repository state before committing
git status --short
git diff --cached --stat
git diff --cached --name-only
```

## Important limitations / next milestones

- The six zero prices are treated as unavailable for analysis based on a documented project assumption; verify the source's semantics if authoritative metadata becomes available.
- The analytics fact table stores the current value per product-month. The loader upserts changed values, so it does **not** preserve every revision of a previously published month. Raw snapshots are retained locally, but source-version history is not yet modeled in PostgreSQL.
- The loader uses upserts and a transaction, but the pipeline is not yet a fully orchestrated production system. Scheduling, task retries, observability, reconciliation for removed source rows, and deployment remain future work.
- The monthly `LAG(..., 12)` comparison assumes complete monthly rows for each product. For missing months, align observations by explicit dates instead of assuming twelve rows always means twelve calendar months.
- Do not commit `.venv/`, passwords, `.env` files, database dumps, or large raw snapshots. See [`docs/GIT_WORKFLOW.md`](docs/GIT_WORKFLOW.md).

## Learning philosophy

Each step should answer four questions: What did we build? Why do we need it? How does it work? How do we test that it behaves correctly? Use the documentation as a memory aid, but revisit the code and re-run the experiments instead of treating this README as a substitute for practice.

## Engineering documentation

- [Historical snapshot replay](docs/SNAPSHOT_REPLAY.md)
