from __future__ import annotations

from dataclasses import dataclass

import asyncpg


@dataclass(frozen=True, slots=True)
class RoleCombinationRow:
    id: int
    guild_id: int
    primary_role_id: int
    secondary_role_id: int
    combined_role_id: int


class RoleCombinationsRepo:
    @staticmethod
    async def list_by_guild(conn: asyncpg.Connection, guild_id: int) -> list[RoleCombinationRow]:
        rows = await conn.fetch(
            """
            SELECT id, guild_id, primary_role_id, secondary_role_id, combined_role_id
              FROM role_combinations
             WHERE guild_id = $1
             ORDER BY primary_role_id, secondary_role_id;
            """,
            guild_id,
        )
        return [
            RoleCombinationRow(
                id=int(row["id"]),
                guild_id=int(row["guild_id"]),
                primary_role_id=int(row["primary_role_id"]),
                secondary_role_id=int(row["secondary_role_id"]),
                combined_role_id=int(row["combined_role_id"]),
            )
            for row in rows
        ]

    @staticmethod
    async def upsert(
        conn: asyncpg.Connection,
        *,
        guild_id: int,
        primary_role_id: int,
        secondary_role_id: int,
        combined_role_id: int,
    ) -> None:
        await conn.execute(
            """
            INSERT INTO role_combinations (
              guild_id, primary_role_id, secondary_role_id, combined_role_id
            )
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id, primary_role_id, secondary_role_id) DO UPDATE
              SET combined_role_id = EXCLUDED.combined_role_id,
                  updated_at = now();
            """,
            guild_id,
            primary_role_id,
            secondary_role_id,
            combined_role_id,
        )

    @staticmethod
    async def delete(
        conn: asyncpg.Connection,
        *,
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
            guild_id,
            primary_role_id,
            secondary_role_id,
        )
        return result.startswith("DELETE ") and not result.endswith(" 0")
