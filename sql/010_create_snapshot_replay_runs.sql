CREATE TABLE IF NOT EXISTS audit.snapshot_replay_run (
    replay_run_id UUID PRIMARY KEY,

    -- What the operator requested, even if validation fails.
    requested_snapshot_filename TEXT NOT NULL
        CHECK (LENGTH(TRIM(requested_snapshot_filename)) > 0),

    -- NULL allows us to record attempts involving unregistered snapshots.
    snapshot_id BIGINT
        REFERENCES audit.source_snapshot(snapshot_id)
        ON DELETE SET NULL,

    trigger_source TEXT NOT NULL DEFAULT 'cli'
        CHECK (trigger_source IN ('cli', 'airflow')),

    airflow_dag_run_id TEXT,

    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'succeeded', 'failed')),

    output_directory TEXT,

    -- Identity of the validated input.
    source_raw_sha256 TEXT
        CHECK (
            source_raw_sha256 IS NULL
            OR source_raw_sha256 ~ '^[0-9a-f]{64}$'
        ),

    source_semantic_sha256 TEXT
        CHECK (
            source_semantic_sha256 IS NULL
            OR source_semantic_sha256 ~ '^[0-9a-f]{64}$'
        ),

    semantic_hash_version SMALLINT
        CHECK (
            semantic_hash_version IS NULL
            OR semantic_hash_version >= 1
        ),

    -- Results of normalization and cleaning.
    normalized_row_count BIGINT
        CHECK (
            normalized_row_count IS NULL
            OR normalized_row_count >= 0
        ),

    analytics_row_count BIGINT
        CHECK (
            analytics_row_count IS NULL
            OR analytics_row_count >= 0
        ),

    normalized_sha256 TEXT
        CHECK (
            normalized_sha256 IS NULL
            OR normalized_sha256 ~ '^[0-9a-f]{64}$'
        ),

    analytics_sha256 TEXT
        CHECK (
            analytics_sha256 IS NULL
            OR analytics_sha256 ~ '^[0-9a-f]{64}$'
        ),

    started_at_utc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at_utc TIMESTAMPTZ,

    error_message TEXT,

    CONSTRAINT ck_snapshot_replay_run_timestamps
        CHECK (
            (
                status = 'running'
                AND finished_at_utc IS NULL
            )
            OR
            (
                status IN ('succeeded', 'failed')
                AND finished_at_utc IS NOT NULL
            )
        ),

    CONSTRAINT ck_snapshot_replay_success
        CHECK (
            status <> 'succeeded'
            OR (
                snapshot_id IS NOT NULL
                AND source_raw_sha256 IS NOT NULL
                AND source_semantic_sha256 IS NOT NULL
                AND semantic_hash_version IS NOT NULL
                AND output_directory IS NOT NULL
                AND normalized_row_count IS NOT NULL
                AND analytics_row_count IS NOT NULL
                AND normalized_sha256 IS NOT NULL
                AND analytics_sha256 IS NOT NULL
                AND error_message IS NULL
            )
        ),

    CONSTRAINT ck_snapshot_replay_failure
        CHECK (
            status <> 'failed'
            OR error_message IS NOT NULL
        )
);

CREATE INDEX IF NOT EXISTS ix_snapshot_replay_run_snapshot
    ON audit.snapshot_replay_run (
        snapshot_id,
        started_at_utc DESC
    );

CREATE INDEX IF NOT EXISTS ix_snapshot_replay_run_status
    ON audit.snapshot_replay_run (
        status,
        started_at_utc DESC
    );

GRANT USAGE ON SCHEMA audit TO pricepulse_dev;

GRANT SELECT, INSERT, UPDATE
ON audit.snapshot_replay_run
TO pricepulse_dev;
