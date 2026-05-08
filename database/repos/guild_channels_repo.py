# database\repos\guild_channels_repo.py

import asyncpg
from typing import Optional

class GuildChannelsRepo:
    @staticmethod
    async def get(conn: asyncpg.Connection, guild_id: int, key: str) -> Optional[int]:
        r = await conn.fetchrow(
            "SELECT channel_id FROM guild_channels WHERE guild_id = $1 AND key = $2;",
            guild_id, key
        )
        return int(r["channel_id"]) if r else None

    @staticmethod
    async def get_all(conn: asyncpg.Connection, guild_id: int) -> dict[str, int]:
        rows = await conn.fetch(
            "SELECT key, channel_id FROM guild_channels WHERE guild_id = $1;",
            guild_id
        )
        return {str(r["key"]): int(r["channel_id"]) for r in rows}

    @staticmethod
    async def upsert(conn: asyncpg.Connection, guild_id: int, key: str, channel_id: int) -> None:
        await conn.execute(
            """
            INSERT INTO guild_channels (guild_id, key, channel_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id, key) DO UPDATE
              SET channel_id = EXCLUDED.channel_id,
                  updated_at = now();
            """,
            guild_id, key, channel_id
        )

    @staticmethod
    async def delete(conn: asyncpg.Connection, guild_id: int, key: str) -> bool:
        res = await conn.execute(
            "DELETE FROM guild_channels WHERE guild_id = $1 AND key = $2;",
            guild_id, key
        )
        return res.startswith("DELETE ") and not res.endswith(" 0")
