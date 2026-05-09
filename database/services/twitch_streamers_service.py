from __future__ import annotations

from database.repos.guilds_repo import GuildsRepo
from database.repos.twitch_streamers_repo import TwitchStreamersRepo


class TwitchStreamersDbService:
    def __init__(self, db) -> None:
        self._db = db

    async def add_streamer(self, *, guild_id: int, guild_name: str | None, streamer_login: str) -> bool:
        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            return await TwitchStreamersRepo.insert(
                conn,
                guild_id=guild_id,
                streamer_login=streamer_login,
            )

    async def remove_streamer(self, *, guild_id: int, streamer_login: str) -> bool:
        async with self._db.transaction() as conn:
            return await TwitchStreamersRepo.delete(
                conn,
                guild_id=guild_id,
                streamer_login=streamer_login,
            )

    async def list_streamers(self, guild_id: int) -> list[str]:
        async with self._db.acquire() as conn:
            rows = await TwitchStreamersRepo.list_by_guild(conn, guild_id)
        return [row.streamer_login for row in rows]
