CREATE TABLE IF NOT EXISTS audit.schema_migration (
    filename TEXT PRIMARY KEY,
    checksum TEXT NOT NULL,
    applied_at_utc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
