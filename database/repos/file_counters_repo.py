from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import asyncpg


@dataclass(frozen=True, slots=True)
class FileCounterRow:
    guild_id: int
    channel_id: int
    message_id: int
    added_count: int
    completed_count: int


class FileCountersRepo:
    @staticmethod
    def _row_to_model(row: asyncpg.Record) -> FileCounterRow:
        return FileCounterRow(
            guild_id=int(row["guild_id"]),
            channel_id=int(row["channel_id"]),
            message_id=int(row["message_id"]),
            added_count=int(row["added_count"]),
            completed_count=int(row["completed_count"]),
        )

    @classmethod
    async def get(
        cls,
        conn: asyncpg.Connection,
        guild_id: int,
        channel_id: int,
    ) -> Optional[FileCounterRow]:
        row = await conn.fetchrow(
            """
            SELECT guild_id, channel_id, message_id, added_count, completed_count
              FROM file_counters
             WHERE guild_id = $1
               AND channel_id = $2;
            """,
            guild_id,
            channel_id,
        )
        return cls._row_to_model(row) if row else None

    @classmethod
    async def list_all(cls, conn: asyncpg.Connection) -> list[FileCounterRow]:
        rows = await conn.fetch(
            """
            SELECT guild_id, channel_id, message_id, added_count, completed_count
              FROM file_counters
             ORDER BY guild_id, channel_id;
            """
        )
        return [cls._row_to_model(row) for row in rows]

    @classmethod
    async def upsert_reset(
        cls,
        conn: asyncpg.Connection,
        guild_id: int,
        channel_id: int,
        message_id: int,
    ) -> FileCounterRow:
        row = await conn.fetchrow(
            """
            INSERT INTO file_counters (
              guild_id, channel_id, message_id, added_count, completed_count
            )
            VALUES ($1, $2, $3, 0, 0)
            ON CONFLICT (guild_id, channel_id) DO UPDATE
              SET message_id = EXCLUDED.message_id,
                  added_count = 0,
                  completed_count = 0,
                  updated_at = now()
            RETURNING guild_id, channel_id, message_id, added_count, completed_count;
            """,
            guild_id,
            channel_id,
            message_id,
        )
        return cls._row_to_model(row)

    @classmethod
    async def increment(
        cls,
        conn: asyncpg.Connection,
        guild_id: int,
        channel_id: int,
        *,
        added_delta: int,
        completed_delta: int,
    ) -> Optional[FileCounterRow]:
        row = await conn.fetchrow(
            """
            UPDATE file_counters
               SET added_count = added_count + $3,
                   completed_count = completed_count + $4,
                   updated_at = now()
             WHERE guild_id = $1
               AND channel_id = $2
            RETURNING guild_id, channel_id, message_id, added_count, completed_count;
            """,
            guild_id,
            channel_id,
            added_delta,
            completed_delta,
        )
        return cls._row_to_model(row) if row else None
