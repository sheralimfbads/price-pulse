
import os
from dataclasses import dataclass
from functools import lru_cache


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return int(raw)


@dataclass(frozen=True)
class Settings:
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    db_connect_timeout: int


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    password = os.getenv("API_DB_PASSWORD") or os.getenv("DB_PASSWORD")
    if not password:
        raise RuntimeError(
            "API_DB_PASSWORD or DB_PASSWORD must be set"
        )

    return Settings(
        db_host=os.getenv("DB_HOST", "localhost"),
        db_port=env_int("DB_PORT", 5432),
        db_name=os.getenv("DB_NAME", "pricepulse"),
        db_user=os.getenv("API_DB_USER", os.getenv("DB_USER", "pricepulse_api")),
        db_password=password,
        db_connect_timeout=env_int("DB_CONNECT_TIMEOUT", 5),
    )
