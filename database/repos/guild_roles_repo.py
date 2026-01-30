# database\repos\guild_roles_repo.py

import asyncpg
from typing import Optional

class GuildRolesRepo:
    @staticmethod
    async def get(conn: asyncpg.Connection, guild_id: int, key: str) -> Optional[int]:
        r = await conn.fetchrow(
            "SELECT role_id FROM guild_roles WHERE guild_id = $1 AND key = $2;",
            guild_id, key
        )
        return int(r["role_id"]) if r else None
    
    @staticmethod
    async def get_all(conn: asyncpg.Connection, guild_id: int) -> dict[str, int]:
        rows = await conn.fetch(
            "SELECT key, role_id FROM guild_roles WHERE guild_id = $1;",
            guild_id
        )
        return {str(r["key"]): int(r["role_id"]) for r in rows}

    @staticmethod
    async def upsert(conn: asyncpg.Connection, guild_id: int, key: str, role_id: int, name_cache: str | None) -> None:
        await conn.execute(
            """
            INSERT INTO guild_roles (guild_id, key, role_id, name_cache)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id, key) DO UPDATE
              SET role_id = EXCLUDED.role_id,
                  name_cache = COALESCE(EXCLUDED.name_cache, guild_roles.name_cache),
                  updated_at = now();
            """,
            guild_id, key, role_id, name_cache
        )

    @staticmethod
    async def delete(conn: asyncpg.Connection, guild_id: int, key: str) -> bool:
        res = await conn.execute(
            "DELETE FROM guild_roles WHERE guild_id = $1 AND key = $2;",
            guild_id, key
        )
        return res.startswith("DELETE ") and not res.endswith(" 0")
