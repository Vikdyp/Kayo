# database/repos/quoi_responses_repo.py

from __future__ import annotations

import asyncpg


class QuoiResponsesRepo:

    @staticmethod
    async def increment(
        conn: asyncpg.Connection,
        guild_id: int,
        discord_user_id: int,
    ) -> None:
        await conn.execute(
            """
            INSERT INTO quoi_responses (guild_id, discord_user_id, trigger_count, last_triggered)
            VALUES ($1, $2, 1, now())
            ON CONFLICT (guild_id, discord_user_id)
            DO UPDATE SET trigger_count = quoi_responses.trigger_count + 1,
                          last_triggered = now();
            """,
            guild_id, discord_user_id,
        )

    @staticmethod
    async def get_top(
        conn: asyncpg.Connection,
        guild_id: int,
        limit: int = 10,
    ) -> list[asyncpg.Record]:
        return await conn.fetch(
            """
            SELECT discord_user_id, trigger_count
              FROM quoi_responses
             WHERE guild_id = $1
             ORDER BY trigger_count DESC
             LIMIT $2;
            """,
            guild_id, limit,
        )
