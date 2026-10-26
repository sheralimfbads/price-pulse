
#!/usr/bin/env bash
set -Eeuo pipefail

: "${DB_USER:?DB_USER must be set}"
: "${DB_PASSWORD:?DB_PASSWORD must be set}"

psql \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    --set=ON_ERROR_STOP=1 \
    --set=app_user="$DB_USER" \
    --set=app_password="$DB_PASSWORD" \
    --set=target_db="$POSTGRES_DB" <<'SQL'

CREATE ROLE :"app_user" LOGIN PASSWORD :'app_password';

GRANT CONNECT, TEMP ON DATABASE :"target_db" TO :"app_user";

SQL
