
from collections.abc import Generator

import psycopg
from psycopg.rows import dict_row

from app.config import get_settings


def connect() -> psycopg.Connection:
    settings = get_settings()
    return psycopg.connect(
        host=settings.db_host,
        port=settings.db_port,
        dbname=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
        connect_timeout=settings.db_connect_timeout,
        row_factory=dict_row,
    )


def get_connection() -> Generator[psycopg.Connection, None, None]:
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()
