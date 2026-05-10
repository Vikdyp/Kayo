from __future__ import annotations

import bot


def test_build_postgres_dsn_prefers_direct_dsn(monkeypatch) -> None:
    monkeypatch.setattr(bot, "DATABASE_DSN", "postgresql://direct")

    assert bot._build_postgres_dsn() == "postgresql://direct"


def test_build_postgres_dsn_quotes_reserved_characters(monkeypatch) -> None:
    monkeypatch.setattr(bot, "DATABASE_DSN", None)
    monkeypatch.setattr(
        bot,
        "DATABASE",
        {
            "user": "user@example",
            "password": "p@ss:word/with%",
            "database": "kayo/prod",
            "host": "localhost",
            "port": 5432,
            "ssl": True,
        },
    )

    assert (
        bot._build_postgres_dsn()
        == "postgresql://user%40example:p%40ss%3Aword%2Fwith%25@localhost:5432/kayo%2Fprod?sslmode=require"
    )
