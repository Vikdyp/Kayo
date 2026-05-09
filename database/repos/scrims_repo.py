from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import asyncpg


@dataclass(frozen=True, slots=True)
class ScrimRow:
    id: int
    guild_id: int
    creator_user_id: Optional[int]
    scheduled_at: datetime
    map_name: str
    rank_name: str
    notes: Optional[str]
    team1_user_ids: tuple[int, ...]
    team2_user_ids: tuple[int, ...]
    channel_id: Optional[int]
    message_id: Optional[int]
    status: str


class ScrimsRepo:
    @staticmethod
    def _row_to_model(row: asyncpg.Record) -> ScrimRow:
        return ScrimRow(
            id=int(row["id"]),
            guild_id=int(row["guild_id"]),
            creator_user_id=int(row["creator_user_id"]) if row["creator_user_id"] else None,
            scheduled_at=row["scheduled_at"],
            map_name=str(row["map_name"]),
            rank_name=str(row["rank_name"]),
            notes=str(row["notes"]) if row["notes"] is not None else None,
            team1_user_ids=tuple(int(value) for value in row["team1_user_ids"]),
            team2_user_ids=tuple(int(value) for value in row["team2_user_ids"]),
            channel_id=int(row["channel_id"]) if row["channel_id"] else None,
            message_id=int(row["message_id"]) if row["message_id"] else None,
            status=str(row["status"]),
        )

    @classmethod
    async def create(
        cls,
        conn: asyncpg.Connection,
        *,
        guild_id: int,
        creator_user_id: int,
        scheduled_at: datetime,
        map_name: str,
        rank_name: str,
        notes: Optional[str],
    ) -> ScrimRow:
        row = await conn.fetchrow(
            """
            INSERT INTO scrims (
              guild_id, creator_user_id, scheduled_at, map_name, rank_name,
              notes, team1_user_ids, team2_user_ids
            )
            VALUES ($1, $2, $3, $4, $5, $6, ARRAY[$2]::BIGINT[], '{}'::BIGINT[])
            RETURNING id, guild_id, creator_user_id, scheduled_at, map_name,
                      rank_name, notes, team1_user_ids, team2_user_ids,
                      channel_id, message_id, status;
            """,
            guild_id,
            creator_user_id,
            scheduled_at,
            map_name,
            rank_name,
            notes,
        )
        return cls._row_to_model(row)

    @classmethod
    async def get_by_id(cls, conn: asyncpg.Connection, scrim_id: int) -> Optional[ScrimRow]:
        row = await conn.fetchrow(
            """
            SELECT id, guild_id, creator_user_id, scheduled_at, map_name,
                   rank_name, notes, team1_user_ids, team2_user_ids,
                   channel_id, message_id, status
              FROM scrims
             WHERE id = $1;
            """,
            scrim_id,
        )
        return cls._row_to_model(row) if row else None

    @classmethod
    async def list_active(cls, conn: asyncpg.Connection, *, guild_id: int | None = None) -> list[ScrimRow]:
        if guild_id is None:
            rows = await conn.fetch(
                """
                SELECT id, guild_id, creator_user_id, scheduled_at, map_name,
                       rank_name, notes, team1_user_ids, team2_user_ids,
                       channel_id, message_id, status
                  FROM scrims
                 WHERE status = 'active'
                 ORDER BY scheduled_at, id;
                """
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, guild_id, creator_user_id, scheduled_at, map_name,
                       rank_name, notes, team1_user_ids, team2_user_ids,
                       channel_id, message_id, status
                  FROM scrims
                 WHERE guild_id = $1
                   AND status = 'active'
                 ORDER BY scheduled_at, id;
                """,
                guild_id,
            )
        return [cls._row_to_model(row) for row in rows]

    @classmethod
    async def list_due(cls, conn: asyncpg.Connection, *, now: datetime) -> list[ScrimRow]:
        rows = await conn.fetch(
            """
            SELECT id, guild_id, creator_user_id, scheduled_at, map_name,
                   rank_name, notes, team1_user_ids, team2_user_ids,
                   channel_id, message_id, status
              FROM scrims
             WHERE status = 'active'
               AND scheduled_at <= $1
             ORDER BY scheduled_at, id;
            """,
            now,
        )
        return [cls._row_to_model(row) for row in rows]

    @classmethod
    async def set_message(
        cls,
        conn: asyncpg.Connection,
        *,
        scrim_id: int,
        channel_id: int,
        message_id: int,
    ) -> Optional[ScrimRow]:
        row = await conn.fetchrow(
            """
            UPDATE scrims
               SET channel_id = $2,
                   message_id = $3,
                   updated_at = now()
             WHERE id = $1
            RETURNING id, guild_id, creator_user_id, scheduled_at, map_name,
                      rank_name, notes, team1_user_ids, team2_user_ids,
                      channel_id, message_id, status;
            """,
            scrim_id,
            channel_id,
            message_id,
        )
        return cls._row_to_model(row) if row else None

    @classmethod
    async def add_to_team(
        cls,
        conn: asyncpg.Connection,
        *,
        scrim_id: int,
        user_id: int,
        team: str,
    ) -> Optional[ScrimRow]:
        if team == "team1":
            statement = """
            UPDATE scrims
               SET team1_user_ids = array_append(team1_user_ids, $2),
                   updated_at = now()
             WHERE id = $1
               AND status = 'active'
               AND NOT ($2 = ANY(team1_user_ids))
               AND NOT ($2 = ANY(team2_user_ids))
               AND cardinality(team1_user_ids) < 5
            RETURNING id, guild_id, creator_user_id, scheduled_at, map_name,
                      rank_name, notes, team1_user_ids, team2_user_ids,
                      channel_id, message_id, status;
            """
        elif team == "team2":
            statement = """
            UPDATE scrims
               SET team2_user_ids = array_append(team2_user_ids, $2),
                   updated_at = now()
             WHERE id = $1
               AND status = 'active'
               AND NOT ($2 = ANY(team1_user_ids))
               AND NOT ($2 = ANY(team2_user_ids))
               AND cardinality(team2_user_ids) < 5
            RETURNING id, guild_id, creator_user_id, scheduled_at, map_name,
                      rank_name, notes, team1_user_ids, team2_user_ids,
                      channel_id, message_id, status;
            """
        else:
            raise ValueError("team")

        row = await conn.fetchrow(statement, scrim_id, user_id)
        return cls._row_to_model(row) if row else None

    @classmethod
    async def remove_participant(
        cls,
        conn: asyncpg.Connection,
        *,
        scrim_id: int,
        user_id: int,
    ) -> Optional[ScrimRow]:
        row = await conn.fetchrow(
            """
            UPDATE scrims
               SET team1_user_ids = array_remove(team1_user_ids, $2),
                   team2_user_ids = array_remove(team2_user_ids, $2),
                   updated_at = now()
             WHERE id = $1
               AND status = 'active'
            RETURNING id, guild_id, creator_user_id, scheduled_at, map_name,
                      rank_name, notes, team1_user_ids, team2_user_ids,
                      channel_id, message_id, status;
            """,
            scrim_id,
            user_id,
        )
        return cls._row_to_model(row) if row else None

    @staticmethod
    async def mark_completed(conn: asyncpg.Connection, *, scrim_id: int) -> bool:
        row = await conn.fetchrow(
            """
            UPDATE scrims
               SET status = 'completed',
                   ended_at = now(),
                   updated_at = now()
             WHERE id = $1
               AND status = 'active'
            RETURNING id;
            """,
            scrim_id,
        )
        return row is not None
