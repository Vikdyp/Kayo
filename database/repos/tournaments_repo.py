from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import asyncpg


@dataclass(frozen=True, slots=True)
class TournamentRow:
    id: int
    guild_id: int
    tournament_name: str
    max_teams: int
    registration_start: datetime
    registration_end: datetime
    tournament_date: datetime
    status: str
    registration_channel_id: Optional[int]
    registration_message_id: Optional[int]


class TournamentsRepo:
    @staticmethod
    def _row_to_model(row: asyncpg.Record) -> TournamentRow:
        return TournamentRow(
            id=int(row["id"]),
            guild_id=int(row["guild_id"]),
            tournament_name=str(row["tournament_name"]),
            max_teams=int(row["max_teams"]),
            registration_start=row["registration_start"],
            registration_end=row["registration_end"],
            tournament_date=row["tournament_date"],
            status=str(row["status"]),
            registration_channel_id=int(row["registration_channel_id"]) if row["registration_channel_id"] else None,
            registration_message_id=int(row["registration_message_id"]) if row["registration_message_id"] else None,
        )

    @classmethod
    async def get_active(cls, conn: asyncpg.Connection, guild_id: int) -> Optional[TournamentRow]:
        row = await conn.fetchrow(
            """
            SELECT id, guild_id, tournament_name, max_teams, registration_start,
                   registration_end, tournament_date, status,
                   registration_channel_id, registration_message_id
              FROM tournaments
             WHERE guild_id = $1
               AND status = 'active'
             ORDER BY created_at DESC
             LIMIT 1;
            """,
            guild_id,
        )
        return cls._row_to_model(row) if row else None

    @classmethod
    async def get_by_id(cls, conn: asyncpg.Connection, tournament_id: int) -> Optional[TournamentRow]:
        row = await conn.fetchrow(
            """
            SELECT id, guild_id, tournament_name, max_teams, registration_start,
                   registration_end, tournament_date, status,
                   registration_channel_id, registration_message_id
              FROM tournaments
             WHERE id = $1;
            """,
            tournament_id,
        )
        return cls._row_to_model(row) if row else None

    @classmethod
    async def create(
        cls,
        conn: asyncpg.Connection,
        *,
        guild_id: int,
        tournament_name: str,
        max_teams: int,
        registration_start: datetime,
        registration_end: datetime,
        tournament_date: datetime,
    ) -> TournamentRow:
        row = await conn.fetchrow(
            """
            INSERT INTO tournaments (
              guild_id, tournament_name, max_teams, registration_start,
              registration_end, tournament_date, status
            )
            VALUES ($1, $2, $3, $4, $5, $6, 'active')
            RETURNING id, guild_id, tournament_name, max_teams, registration_start,
                      registration_end, tournament_date, status,
                      registration_channel_id, registration_message_id;
            """,
            guild_id,
            tournament_name,
            max_teams,
            registration_start,
            registration_end,
            tournament_date,
        )
        return cls._row_to_model(row)

    @classmethod
    async def set_registration_message(
        cls,
        conn: asyncpg.Connection,
        *,
        tournament_id: int,
        channel_id: int,
        message_id: int,
    ) -> Optional[TournamentRow]:
        row = await conn.fetchrow(
            """
            UPDATE tournaments
               SET registration_channel_id = $2,
                   registration_message_id = $3,
                   updated_at = now()
             WHERE id = $1
            RETURNING id, guild_id, tournament_name, max_teams, registration_start,
                      registration_end, tournament_date, status,
                      registration_channel_id, registration_message_id;
            """,
            tournament_id,
            channel_id,
            message_id,
        )
        return cls._row_to_model(row) if row else None

    @classmethod
    async def close_active(cls, conn: asyncpg.Connection, guild_id: int) -> bool:
        row = await conn.fetchrow(
            """
            UPDATE tournaments
               SET status = 'closed',
                   closed_at = now(),
                   updated_at = now()
             WHERE guild_id = $1
               AND status = 'active'
            RETURNING id;
            """,
            guild_id,
        )
        return row is not None
