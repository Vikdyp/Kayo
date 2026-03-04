# database/repos/streamer_partners_repo.py

from __future__ import annotations

import asyncpg


class StreamerPartnersRepo:

    @staticmethod
    async def add(conn: asyncpg.Connection, guild_id: int, streamer_name: str) -> None:
        await conn.execute(
            """
            INSERT INTO streamer_partners (guild_id, streamer_name)
            VALUES ($1, $2)
            ON CONFLICT DO NOTHING;
            """,
            guild_id, streamer_name.lower(),
        )

    @staticmethod
    async def remove(conn: asyncpg.Connection, guild_id: int, streamer_name: str) -> bool:
        result = await conn.execute(
            """
            DELETE FROM streamer_partners
             WHERE guild_id = $1
               AND streamer_name = $2;
            """,
            guild_id, streamer_name.lower(),
        )
        return result.endswith("1")

    @staticmethod
    async def list_all(conn: asyncpg.Connection, guild_id: int) -> list[str]:
        rows = await conn.fetch(
            "SELECT streamer_name FROM streamer_partners WHERE guild_id = $1;",
            guild_id,
        )
        return [r["streamer_name"] for r in rows]
