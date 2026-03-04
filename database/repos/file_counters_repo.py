# database/repos/file_counters_repo.py

from __future__ import annotations

from typing import Optional
import asyncpg


class FileCountersRepo:

    @staticmethod
    async def get(
        conn: asyncpg.Connection, guild_id: int, channel_id: int
    ) -> Optional[asyncpg.Record]:
        return await conn.fetchrow(
            """
            SELECT message_id, ajouter_count, terminer_count
              FROM file_counters
             WHERE guild_id = $1
               AND channel_id = $2;
            """,
            guild_id, channel_id,
        )

    @staticmethod
    async def upsert(
        conn: asyncpg.Connection,
        guild_id: int,
        channel_id: int,
        message_id: int,
    ) -> None:
        await conn.execute(
            """
            INSERT INTO file_counters (guild_id, channel_id, message_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id, channel_id) DO UPDATE
              SET message_id = EXCLUDED.message_id,
                  updated_at = now();
            """,
            guild_id, channel_id, message_id,
        )

    @staticmethod
    async def increment(
        conn: asyncpg.Connection,
        guild_id: int,
        channel_id: int,
        ajouter: bool = False,
        terminer: bool = False,
    ) -> Optional[asyncpg.Record]:
        parts = []
        if ajouter:
            parts.append("ajouter_count = ajouter_count + 1")
        if terminer:
            parts.append("terminer_count = terminer_count + 1")
        if not parts:
            return None
        parts.append("updated_at = now()")
        set_clause = ", ".join(parts)
        return await conn.fetchrow(
            f"""
            UPDATE file_counters
               SET {set_clause}
             WHERE guild_id = $1 AND channel_id = $2
            RETURNING ajouter_count, terminer_count;
            """,
            guild_id, channel_id,
        )

    @staticmethod
    async def reset(
        conn: asyncpg.Connection,
        guild_id: int,
        channel_id: int,
        message_id: int,
    ) -> None:
        await conn.execute(
            """
            UPDATE file_counters
               SET ajouter_count = 0, terminer_count = 0,
                   message_id = $3, updated_at = now()
             WHERE guild_id = $1 AND channel_id = $2;
            """,
            guild_id, channel_id, message_id,
        )
