# database\migrate.py

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import asyncpg
from dotenv import load_dotenv

from database.dsn import build_database_dsn_from_env
from database.engine import Db, DbConfig

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

load_dotenv()


async def _ensure_migrations_table(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )


def _iter_migration_files() -> Iterable[Path]:
    files = sorted(p for p in MIGRATIONS_DIR.glob("*.sql") if p.is_file())
    return files


async def _is_applied(conn: asyncpg.Connection, version: str) -> bool:
    row = await conn.fetchrow(
        "SELECT 1 FROM schema_migrations WHERE version = $1;",
        version,
    )
    return row is not None


async def _mark_applied(conn: asyncpg.Connection, version: str) -> None:
    await conn.execute(
        "INSERT INTO schema_migrations(version) VALUES ($1);",
        version,
    )


async def run_migrations(db: Db) -> None:
    async with db.transaction() as conn:
        await _ensure_migrations_table(conn)

    for path in _iter_migration_files():
        version = path.name
        async with db.transaction() as conn:
            if await _is_applied(conn, version):
                continue

            sql = path.read_text(encoding="utf-8").strip()
            if not sql:
                await _mark_applied(conn, version)
                continue

            # One migration file per transaction
            await conn.execute(sql)
            await _mark_applied(conn, version)

# CLI simple: python -m database.migrate
async def _amain() -> None:
    try:
        dsn = build_database_dsn_from_env()
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    db = Db(DbConfig(dsn=dsn))
    await db.open()
    try:
        await run_migrations(db)
        print("Migrations applied.")
    finally:
        await db.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(_amain())
