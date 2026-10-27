
#!/usr/bin/env bash
set -Eeuo pipefail

psql \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    --set=ON_ERROR_STOP=1 \
    --set=app_user="$DB_USER" \
    --set=owner_role="$POSTGRES_USER" \
    --set=target_db="$POSTGRES_DB" <<'SQL'

GRANT CONNECT, TEMP ON DATABASE :"target_db" TO :"app_user";

GRANT USAGE ON SCHEMA staging, analytics, audit TO :"app_user";

GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA staging, analytics, audit
TO :"app_user";

GRANT USAGE, SELECT, UPDATE
ON ALL SEQUENCES IN SCHEMA analytics, audit
TO :"app_user";

ALTER DEFAULT PRIVILEGES FOR ROLE :"owner_role"
IN SCHEMA staging, analytics, audit
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"app_user";

ALTER DEFAULT PRIVILEGES FOR ROLE :"owner_role"
IN SCHEMA analytics, audit
GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO :"app_user";

SQL
