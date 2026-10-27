
import hashlib
import os
import sys
from pathlib import Path

import psycopg
from psycopg import sql


ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "sql"

# Applied once, in dependency order. Files use IF NOT EXISTS / ADD COLUMN IF NOT EXISTS.
ONCE_MIGRATIONS = [
    "001_create_schema.sql",
    "005_create_analytics_model.sql",
    "008_create_snapshot_history.sql",
    "009_version_semantic_hash.sql",
    "010_create_snapshot_replay_runs.sql",
    "013_schema_migrations.sql",
]

# Views are replaced so existing databases pick up definition changes.
REPEATABLE_MIGRATIONS = [
    "011_create_analytics_views.sql",
    "012_price_change_rankings.sql",
]


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} must be set for migrations")
    return value


def connect_as_admin():
    return psycopg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "pricepulse"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=require_env("POSTGRES_ADMIN_PASSWORD"),
    )


def file_checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def apply_sql(cur, path: Path) -> None:
    statement = path.read_text(encoding="utf-8")
    cur.execute(statement)


def ensure_role(cur, role_name: str, password: str) -> None:
    cur.execute(
        "SELECT 1 FROM pg_roles WHERE rolname = %s",
        (role_name,),
    )
    if cur.fetchone() is None:
        cur.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(role_name),
                sql.Literal(password),
            )
        )
    else:
        cur.execute(
            sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(role_name),
                sql.Literal(password),
            )
        )


def grant_pipeline_privileges(cur, app_user: str) -> None:
    role = sql.Identifier(app_user)
    cur.execute(
        sql.SQL("GRANT CONNECT, TEMP ON DATABASE {} TO {}").format(
            sql.Identifier(os.getenv("DB_NAME", "pricepulse")),
            role,
        )
    )
    cur.execute(
        sql.SQL("GRANT USAGE ON SCHEMA staging, analytics, audit TO {}").format(role)
    )
    cur.execute(
        sql.SQL(
            "GRANT SELECT, INSERT, UPDATE, DELETE "
            "ON ALL TABLES IN SCHEMA staging, analytics, audit TO {}"
        ).format(role)
    )
    cur.execute(
        sql.SQL(
            "GRANT USAGE, SELECT, UPDATE "
            "ON ALL SEQUENCES IN SCHEMA analytics, audit TO {}"
        ).format(role)
    )


def grant_api_privileges(cur, api_user: str) -> None:
    role = sql.Identifier(api_user)
    cur.execute(
        sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
            sql.Identifier(os.getenv("DB_NAME", "pricepulse")),
            role,
        )
    )
    cur.execute(
        sql.SQL("GRANT USAGE ON SCHEMA analytics, audit TO {}").format(role)
    )
    cur.execute(
        sql.SQL(
            "GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO {}"
        ).format(role)
    )
    cur.execute(
        sql.SQL("GRANT SELECT ON audit.source_snapshot TO {}").format(role)
    )
    cur.execute(
        sql.SQL("REVOKE ALL ON SCHEMA staging FROM {}").format(role)
    )


def already_applied(cur, filename: str, checksum: str) -> bool:
    cur.execute(
        """
        SELECT checksum
        FROM audit.schema_migration
        WHERE filename = %s
        """,
        (filename,),
    )
    row = cur.fetchone()
    return row is not None and row[0] == checksum


def record_migration(cur, filename: str, checksum: str) -> None:
    cur.execute(
        """
        INSERT INTO audit.schema_migration (filename, checksum)
        VALUES (%s, %s)
        ON CONFLICT (filename)
        DO UPDATE SET
            checksum = EXCLUDED.checksum,
            applied_at_utc = CURRENT_TIMESTAMP
        """,
        (filename, checksum),
    )


def apply_once(cur, filename: str) -> str:
    path = SQL_DIR / filename
    checksum = file_checksum(path)

    if filename == "013_schema_migrations.sql":
        apply_sql(cur, path)
        record_migration(cur, filename, checksum)
        return "applied"

    cur.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'audit'
          AND table_name = 'schema_migration'
        """
    )
    tracking_ready = cur.fetchone() is not None

    if tracking_ready and already_applied(cur, filename, checksum):
        return "skipped"

    apply_sql(cur, path)

    cur.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'audit'
          AND table_name = 'schema_migration'
        """
    )
    if cur.fetchone() is not None:
        record_migration(cur, filename, checksum)

    return "applied"


def apply_repeatable(cur, filename: str) -> str:
    path = SQL_DIR / filename
    checksum = file_checksum(path)
    apply_sql(cur, path)

    cur.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'audit'
          AND table_name = 'schema_migration'
        """
    )
    if cur.fetchone() is not None:
        record_migration(cur, filename, checksum)
    return "applied"


def main() -> None:
    app_user = os.getenv("DB_USER", "pricepulse_dev")
    app_password = require_env("DB_PASSWORD")
    api_user = os.getenv("API_DB_USER", "pricepulse_api")
    api_password = require_env("API_DB_PASSWORD")

    results: list[tuple[str, str]] = []

    with connect_as_admin() as conn:
        conn.autocommit = False
        with conn.cursor() as cur:
            ensure_role(cur, app_user, app_password)
            ensure_role(cur, api_user, api_password)

            for filename in ONCE_MIGRATIONS:
                results.append((filename, apply_once(cur, filename)))

            for filename in REPEATABLE_MIGRATIONS:
                results.append((filename, apply_repeatable(cur, filename)))

            grant_pipeline_privileges(cur, app_user)
            grant_api_privileges(cur, api_user)

        conn.commit()

    print("=== PRICEPULSE MIGRATIONS ===")
    for filename, status in results:
        print(f"{status}: {filename}")
    print(f"Pipeline role: {app_user}")
    print(f"API role: {api_user}")
    print("Migration transaction committed successfully.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("MIGRATION FAILED", file=sys.stderr)
        raise
