# database\engine.py

from __future__ import annotations

import asyncpg
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator, Optional


@dataclass(frozen=True)
class DbConfig:
    dsn: str
    min_size: int = 1
    max_size: int = 10
    command_timeout: float = 30.0


class Db:
    """
    Infra DB: pool + context managers.
    - Aucun SQL métier ici.
    - Les repos reçoivent une Connection (conn).
    """

    def __init__(self, cfg: DbConfig) -> None:
        self._cfg = cfg
        self._pool: Optional[asyncpg.Pool] = None

    async def open(self) -> None:
        if self._pool is not None:
            return
        self._pool = await asyncpg.create_pool(
            dsn=self._cfg.dsn,
            min_size=self._cfg.min_size,
            max_size=self._cfg.max_size,
            command_timeout=self._cfg.command_timeout,
        )

    async def close(self) -> None:
        if self._pool is None:
            return
        await self._pool.close()
        self._pool = None

    def _require_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("DB pool is not initialized. Call await db.open() first.")
        return self._pool

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[asyncpg.Connection]:
        pool = self._require_pool()
        conn = await pool.acquire()
        try:
            yield conn
        finally:
            await pool.release(conn)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[asyncpg.Connection]:
        """
        Transaction atomique.
        Les repos ne démarrent pas de transaction eux-mêmes.
        """
        async with self.acquire() as conn:
            tx = conn.transaction()
            await tx.start()
            try:
                yield conn
            except Exception:
                await tx.rollback()
                raise
            else:
                await tx.commit()
