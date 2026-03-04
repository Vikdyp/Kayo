# database/services/quoi_responses_service.py

from __future__ import annotations

from dataclasses import dataclass

from database.repos.guilds_repo import GuildsRepo
from database.repos.quoi_responses_repo import QuoiResponsesRepo


@dataclass(frozen=True)
class QuoiLeaderboardEntry:
    discord_user_id: int
    trigger_count: int


class QuoiResponsesService:
    def __init__(self, db):
        self._db = db

    async def increment(self, guild_id: int, guild_name: str | None, discord_user_id: int) -> None:
        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            await QuoiResponsesRepo.increment(conn, guild_id, discord_user_id)

    async def get_top(self, guild_id: int, limit: int = 10) -> list[QuoiLeaderboardEntry]:
        async with self._db.acquire() as conn:
            rows = await QuoiResponsesRepo.get_top(conn, guild_id, limit)
            return [
                QuoiLeaderboardEntry(
                    discord_user_id=r["discord_user_id"],
                    trigger_count=r["trigger_count"],
                )
                for r in rows
            ]
