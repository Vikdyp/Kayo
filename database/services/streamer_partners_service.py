# database/services/streamer_partners_service.py

from __future__ import annotations

from typing import Optional

from database.repos.guilds_repo import GuildsRepo
from database.repos.streamer_partners_repo import StreamerPartnersRepo


class StreamerPartnersService:
    def __init__(self, db):
        self._db = db

    async def add(self, guild_id: int, guild_name: Optional[str], streamer_name: str) -> None:
        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            await StreamerPartnersRepo.add(conn, guild_id, streamer_name)

    async def remove(self, guild_id: int, streamer_name: str) -> bool:
        async with self._db.transaction() as conn:
            return await StreamerPartnersRepo.remove(conn, guild_id, streamer_name)

    async def list_all(self, guild_id: int) -> list[str]:
        async with self._db.acquire() as conn:
            return await StreamerPartnersRepo.list_all(conn, guild_id)
