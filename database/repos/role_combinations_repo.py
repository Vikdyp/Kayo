# database/repos/role_combinations_repo.py

from __future__ import annotations

import asyncpg


class RoleCombinationsRepo:

    @staticmethod
    async def get_all(conn: asyncpg.Connection, guild_id: int) -> list[asyncpg.Record]:
        return await conn.fetch(
            """
            SELECT primary_role_id, secondary_role_id, combined_role_id
              FROM role_combinations
             WHERE guild_id = $1;
            """,
            guild_id,
        )

    @staticmethod
    async def upsert(
        conn: asyncpg.Connection,
        guild_id: int,
        primary_role_id: int,
        secondary_role_id: int,
        combined_role_id: int,
    ) -> None:
        await conn.execute(
            """
            INSERT INTO role_combinations (guild_id, primary_role_id, secondary_role_id, combined_role_id)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id, primary_role_id, secondary_role_id)
            DO UPDATE SET combined_role_id = EXCLUDED.combined_role_id;
            """,
            guild_id, primary_role_id, secondary_role_id, combined_role_id,
        )

    @staticmethod
    async def delete(
        conn: asyncpg.Connection,
        guild_id: int,
        primary_role_id: int,
        secondary_role_id: int,
    ) -> bool:
        result = await conn.execute(
            """
            DELETE FROM role_combinations
             WHERE guild_id = $1
               AND primary_role_id = $2
               AND secondary_role_id = $3;
            """,
            guild_id, primary_role_id, secondary_role_id,
        )
        return result.endswith("1")
