
CREATE SCHEMA IF NOT EXISTS audit;

CREATE TABLE IF NOT EXISTS audit.source_snapshot (
    snapshot_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    snapshot_filename TEXT NOT NULL UNIQUE,
    fetched_at_utc TIMESTAMPTZ NOT NULL,
    source_url TEXT NOT NULL,

    raw_sha256 TEXT NOT NULL
        CHECK (raw_sha256 ~ '^[0-9a-f]{64}$'),

    semantic_sha256 TEXT NOT NULL
        CHECK (semantic_sha256 ~ '^[0-9a-f]{64}$'),

    product_count INTEGER NOT NULL CHECK (product_count >= 0),
    period_count INTEGER NOT NULL CHECK (period_count >= 0),
    observation_count INTEGER NOT NULL CHECK (observation_count >= 0),

    source_metadata JSONB NOT NULL,
    registered_at_utc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_source_snapshot_semantic_hash
    ON audit.source_snapshot (semantic_sha256);


CREATE TABLE IF NOT EXISTS audit.source_snapshot_product (
    snapshot_id BIGINT NOT NULL
        REFERENCES audit.source_snapshot(snapshot_id)
        ON DELETE CASCADE,

    product_code TEXT NOT NULL,
    product_name_uz TEXT,
    product_name_ru TEXT,
    product_name_en TEXT,
    product_name_uz_cyrillic TEXT,

    PRIMARY KEY (snapshot_id, product_code)
);


CREATE TABLE IF NOT EXISTS audit.source_snapshot_price_observation (
    snapshot_id BIGINT NOT NULL,
    product_code TEXT NOT NULL,
    period DATE NOT NULL,
    source_period_key TEXT NOT NULL,
    source_price_uzs_per_kg NUMERIC,

    PRIMARY KEY (snapshot_id, product_code, period),

    FOREIGN KEY (snapshot_id, product_code)
        REFERENCES audit.source_snapshot_product (
            snapshot_id,
            product_code
        )
        ON DELETE CASCADE,

    CONSTRAINT ck_snapshot_period_month_start
        CHECK (EXTRACT(DAY FROM period) = 1)
);


CREATE INDEX IF NOT EXISTS ix_snapshot_prices_product_period
    ON audit.source_snapshot_price_observation (
        product_code,
        period
    );


-- Allow the application role to read and register snapshots.
GRANT USAGE ON SCHEMA audit TO pricepulse_dev;

GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA audit
TO pricepulse_dev;

GRANT USAGE, SELECT, UPDATE
ON ALL SEQUENCES IN SCHEMA audit
TO pricepulse_dev;


-- Apply equivalent permissions to future audit tables and sequences
-- created by the postgres role.
ALTER DEFAULT PRIVILEGES FOR ROLE postgres
IN SCHEMA audit
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO pricepulse_dev;

ALTER DEFAULT PRIVILEGES FOR ROLE postgres
IN SCHEMA audit
GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO pricepulse_dev;
