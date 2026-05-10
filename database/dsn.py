from __future__ import annotations

import os
from typing import Mapping
from urllib.parse import quote


def env_bool(values: Mapping[str, str], name: str, default: bool = False) -> bool:
    value = values.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"true", "1", "t", "yes", "y", "on"}


def build_database_dsn_from_env(env: Mapping[str, str] | None = None) -> str:
    values = env or os.environ
    direct_dsn = values.get("DATABASE_URL") or values.get("POSTGRES_DSN")
    if direct_dsn:
        return direct_dsn

    user = values.get("DATABASE_USER")
    password = values.get("DATABASE_PASSWORD")
    host = values.get("DATABASE_HOST")
    test_mode = env_bool(values, "TEST_MODE")
    database_key = "DATABASE_TEST_NAME" if test_mode else "DATABASE_NAME"
    name = values.get(database_key)
    port = values.get("DATABASE_PORT", "5432")
    ssl_enabled = env_bool(values, "DATABASE_SSL")

    missing = [
        key
        for key, value in {
            "DATABASE_USER": user,
            "DATABASE_PASSWORD": password,
            "DATABASE_HOST": host,
            database_key: name,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing database config env vars: {', '.join(missing)}")

    dsn = f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}@{host}:{port}/{quote(name, safe='')}"
    if ssl_enabled:
        dsn += "?sslmode=require"
    return dsn
