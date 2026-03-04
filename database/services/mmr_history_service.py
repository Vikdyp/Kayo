# database/services/mmr_history_service.py

from __future__ import annotations

import re
import logging
from datetime import datetime
from typing import Any, Optional

from database.repos.mmr_history_repo import MmrHistoryRepo
from database.repos.valorant_info_repo import ValorantInfoRepo

logger = logging.getLogger(__name__)


class MmrHistoryService:
    def __init__(self, db):
        self._db = db

    async def _get_user_pk(self, discord_id: int) -> Optional[int]:
        async with self._db.acquire() as conn:
            return await ValorantInfoRepo._get_user_pk(conn, discord_id)

    async def ensure_partitions(self, season: int, act: int) -> None:
        async with self._db.transaction() as conn:
            await MmrHistoryRepo.ensure_partitions(conn, season, act)

    async def insert_entry(
        self,
        user_id: int,
        season: int,
        act: int,
        recorded_at: datetime,
        elo: int,
        is_win: bool,
    ) -> None:
        async with self._db.transaction() as conn:
            await MmrHistoryRepo.ensure_partitions(conn, season, act)
            await MmrHistoryRepo.insert_entry(
                conn, season, act, user_id, recorded_at, elo, is_win
            )

    async def get_last_row(self, user_id: int) -> Optional[dict]:
        async with self._db.acquire() as conn:
            row = await MmrHistoryRepo.get_last_row(conn, user_id)
            if not row:
                return None
            return dict(row)

    async def get_history(
        self,
        discord_id: int,
        season: Optional[int] = None,
        act: Optional[int] = None,
    ) -> list[dict]:
        user_pk = await self._get_user_pk(discord_id)
        if not user_pk:
            return []
        async with self._db.acquire() as conn:
            rows = await MmrHistoryRepo.get_history(conn, user_pk, season, act)
            return [dict(r) for r in rows]

    async def get_distinct_partitions(self, discord_id: int) -> list[tuple[int, int]]:
        user_pk = await self._get_user_pk(discord_id)
        if not user_pk:
            return []
        async with self._db.acquire() as conn:
            return await MmrHistoryRepo.get_distinct_partitions(conn, user_pk)

    async def get_latest_partition(self) -> Optional[tuple[int, int]]:
        async with self._db.acquire() as conn:
            return await MmrHistoryRepo.get_latest_partition(conn)

    async def get_tracked_players(self) -> list[dict]:
        async with self._db.acquire() as conn:
            rows = await conn.fetch(
                "SELECT user_id, elo FROM valorant_info WHERE tracking_enabled = TRUE"
            )
            return [dict(r) for r in rows]

    async def get_valorant_info(self, user_id: int) -> Optional[dict]:
        async with self._db.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT pseudo, tag, region, puuid FROM valorant_info WHERE user_id = $1",
                user_id,
            )
            return dict(row) if row else None

    async def update_puuid(self, user_id: int, puuid: str) -> None:
        async with self._db.transaction() as conn:
            await conn.execute(
                "UPDATE valorant_info SET puuid = $1 WHERE user_id = $2",
                puuid, user_id,
            )
