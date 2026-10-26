
ALTER TABLE audit.source_snapshot
ADD COLUMN IF NOT EXISTS semantic_hash_version
    SMALLINT NOT NULL DEFAULT 1;
