# database/services/file_counters_service.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from database.repos.guilds_repo import GuildsRepo
from database.repos.file_counters_repo import FileCountersRepo


@dataclass(frozen=True)
class CounterInfo:
    message_id: int
    ajouter_count: int
    terminer_count: int


class FileCountersService:
    def __init__(self, db):
        self._db = db

    async def get(self, guild_id: int, channel_id: int) -> Optional[CounterInfo]:
        async with self._db.acquire() as conn:
            row = await FileCountersRepo.get(conn, guild_id, channel_id)
            if not row:
                return None
            return CounterInfo(
                message_id=row["message_id"],
                ajouter_count=row["ajouter_count"],
                terminer_count=row["terminer_count"],
            )

    async def create_or_update(
        self, guild_id: int, guild_name: Optional[str], channel_id: int, message_id: int
    ) -> None:
        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            await FileCountersRepo.upsert(conn, guild_id, channel_id, message_id)

    async def increment(
        self, guild_id: int, channel_id: int, ajouter: bool = False, terminer: bool = False
    ) -> Optional[CounterInfo]:
        async with self._db.transaction() as conn:
            row = await FileCountersRepo.increment(conn, guild_id, channel_id, ajouter, terminer)
            if not row:
                return None
            return CounterInfo(
                message_id=0,  # not returned by increment
                ajouter_count=row["ajouter_count"],
                terminer_count=row["terminer_count"],
            )

    async def reset(self, guild_id: int, channel_id: int, message_id: int) -> None:
        async with self._db.transaction() as conn:
            await FileCountersRepo.reset(conn, guild_id, channel_id, message_id)
