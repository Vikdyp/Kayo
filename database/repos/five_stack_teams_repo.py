from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import asyncpg


@dataclass(frozen=True, slots=True)
class FiveStackTeamRow:
    code: str
    guild_id: int
    leader_discord_id: int
    visibility: str
    forum_channel_id: Optional[int]
    thread_id: Optional[int]
    voice_channel_id: Optional[int]
    status: str
    created_at: datetime


class FiveStackTeamsRepo:
    @staticmethod
    def _row_to_model(row: asyncpg.Record) -> FiveStackTeamRow:
        return FiveStackTeamRow(
            code=str(row["code"]),
            guild_id=int(row["guild_id"]),
            leader_discord_id=int(row["leader_discord_id"]),
            visibility=str(row["visibility"]),
            forum_channel_id=int(row["forum_channel_id"]) if row["forum_channel_id"] else None,
            thread_id=int(row["thread_id"]) if row["thread_id"] else None,
            voice_channel_id=int(row["voice_channel_id"]) if row["voice_channel_id"] else None,
            status=str(row["status"]),
            created_at=row["created_at"],
        )

    @classmethod
    async def create(
        cls,
        conn: asyncpg.Connection,
        *,
        guild_id: int,
        code: str,
        leader_discord_id: int,
        visibility: str,
        forum_channel_id: int | None,
        thread_id: int | None,
    ) -> FiveStackTeamRow:
        row = await conn.fetchrow(
            """
            INSERT INTO five_stack_teams (
              guild_id, code, leader_discord_id, visibility, forum_channel_id, thread_id
            )
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING code, guild_id, leader_discord_id, visibility, forum_channel_id,
                      thread_id, voice_channel_id, status, created_at;
            """,
            guild_id,
            code,
            leader_discord_id,
            visibility,
            forum_channel_id,
            thread_id,
        )
        return cls._row_to_model(row)

    @classmethod
    async def get(cls, conn: asyncpg.Connection, *, guild_id: int, code: str) -> FiveStackTeamRow | None:
        row = await conn.fetchrow(
            """
            SELECT code, guild_id, leader_discord_id, visibility, forum_channel_id,
                   thread_id, voice_channel_id, status, created_at
              FROM five_stack_teams
             WHERE guild_id = $1
               AND code = $2
               AND status = 'active';
            """,
            guild_id,
            code,
        )
        return cls._row_to_model(row) if row else None

    @classmethod
    async def list_active(cls, conn: asyncpg.Connection, guild_id: int) -> list[FiveStackTeamRow]:
        rows = await conn.fetch(
            """
            SELECT code, guild_id, leader_discord_id, visibility, forum_channel_id,
                   thread_id, voice_channel_id, status, created_at
              FROM five_stack_teams
             WHERE guild_id = $1
               AND status = 'active'
             ORDER BY created_at;
            """,
            guild_id,
        )
        return [cls._row_to_model(row) for row in rows]

    @classmethod
    async def list_older_than(cls, conn: asyncpg.Connection, *, hours: int) -> list[FiveStackTeamRow]:
        rows = await conn.fetch(
            """
            SELECT code, guild_id, leader_discord_id, visibility, forum_channel_id,
                   thread_id, voice_channel_id, status, created_at
              FROM five_stack_teams
             WHERE status = 'active'
               AND created_at < now() - make_interval(hours => $1)
             ORDER BY created_at;
            """,
            hours,
        )
        return [cls._row_to_model(row) for row in rows]

    @staticmethod
    async def update_leader(
        conn: asyncpg.Connection,
        *,
        guild_id: int,
        code: str,
        leader_discord_id: int,
    ) -> bool:
        result = await conn.execute(
            """
            UPDATE five_stack_teams
               SET leader_discord_id = $3,
                   updated_at = now()
             WHERE guild_id = $1
               AND code = $2
               AND status = 'active';
            """,
            guild_id,
            code,
            leader_discord_id,
        )
        return result != "UPDATE 0"

    @staticmethod
    async def set_thread(
        conn: asyncpg.Connection,
        *,
        guild_id: int,
        code: str,
        forum_channel_id: int | None,
        thread_id: int | None,
    ) -> bool:
        result = await conn.execute(
            """
            UPDATE five_stack_teams
               SET forum_channel_id = $3,
                   thread_id = $4,
                   updated_at = now()
             WHERE guild_id = $1
               AND code = $2;
            """,
            guild_id,
            code,
            forum_channel_id,
            thread_id,
        )
        return result != "UPDATE 0"

    @staticmethod
    async def set_voice_channel(
        conn: asyncpg.Connection,
        *,
        guild_id: int,
        code: str,
        voice_channel_id: int | None,
    ) -> bool:
        result = await conn.execute(
            """
            UPDATE five_stack_teams
               SET voice_channel_id = $3,
                   updated_at = now()
             WHERE guild_id = $1
               AND code = $2
               AND status = 'active';
            """,
            guild_id,
            code,
            voice_channel_id,
        )
        return result != "UPDATE 0"

    @staticmethod
    async def mark_deleted(conn: asyncpg.Connection, *, guild_id: int, code: str) -> bool:
        result = await conn.execute(
            """
            UPDATE five_stack_teams
               SET status = 'deleted',
                   updated_at = now()
             WHERE guild_id = $1
               AND code = $2
               AND status = 'active';
            """,
            guild_id,
            code,
        )
        return result != "UPDATE 0"
