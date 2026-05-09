from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from database.repos.file_counters_repo import FileCountersRepo
from database.repos.guilds_repo import GuildsRepo


@dataclass(frozen=True, slots=True)
class FileCounterInfo:
    guild_id: int
    channel_id: int
    message_id: int
    added_count: int
    completed_count: int


class FileCountersService:
    def __init__(self, db) -> None:
        self._db = db

    @staticmethod
    def _to_info(row) -> FileCounterInfo:
        return FileCounterInfo(
            guild_id=row.guild_id,
            channel_id=row.channel_id,
            message_id=row.message_id,
            added_count=row.added_count,
            completed_count=row.completed_count,
        )

    async def get_counter(self, guild_id: int, channel_id: int) -> Optional[FileCounterInfo]:
        async with self._db.acquire() as conn:
            row = await FileCountersRepo.get(conn, guild_id, channel_id)
            return self._to_info(row) if row else None

    async def list_counters(self) -> list[FileCounterInfo]:
        async with self._db.acquire() as conn:
            return [self._to_info(row) for row in await FileCountersRepo.list_all(conn)]

    async def reset_counter(
        self,
        *,
        guild_id: int,
        guild_name: str | None,
        channel_id: int,
        message_id: int,
    ) -> FileCounterInfo:
        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            row = await FileCountersRepo.upsert_reset(conn, guild_id, channel_id, message_id)
            return self._to_info(row)

    async def increment_counter(
        self,
        *,
        guild_id: int,
        channel_id: int,
        added_delta: int = 0,
        completed_delta: int = 0,
    ) -> Optional[FileCounterInfo]:
        if added_delta == 0 and completed_delta == 0:
            return None
        async with self._db.transaction() as conn:
            row = await FileCountersRepo.increment(
                conn,
                guild_id,
                channel_id,
                added_delta=added_delta,
                completed_delta=completed_delta,
            )
            return self._to_info(row) if row else None
