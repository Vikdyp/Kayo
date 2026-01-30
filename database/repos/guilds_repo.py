# database\repos\guilds_repo.py

import asyncpg

class GuildsRepo:
    @staticmethod
    async def ensure_exists(conn: asyncpg.Connection, guild_id: int, name_cache: str | None) -> None:
        await conn.execute(
            """
            INSERT INTO guilds (guild_id, name_cache)
            VALUES ($1, $2)
            ON CONFLICT (guild_id) DO UPDATE
              SET name_cache = COALESCE(EXCLUDED.name_cache, guilds.name_cache),
                  updated_at = now();
            """,
            guild_id, name_cache
        )

    @staticmethod
    async def exists(conn: asyncpg.Connection, guild_id: int) -> bool:
        row = await conn.fetchrow(
            "SELECT 1 FROM guilds WHERE guild_id = $1;",
            guild_id,
        )
        return row is not None