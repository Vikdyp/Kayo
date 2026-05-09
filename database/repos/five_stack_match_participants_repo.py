from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import asyncpg


@dataclass(frozen=True, slots=True)
class FiveStackMatchParticipantRow:
    match_id: int
    discord_member_id: int
    elo_at_match: Optional[int]
    roles_selected: tuple[str, ...]
    entry_type: int
    wait_time_seconds: int


class FiveStackMatchParticipantsRepo:
    @staticmethod
    def _row_to_model(row: asyncpg.Record) -> FiveStackMatchParticipantRow:
        return FiveStackMatchParticipantRow(
            match_id=int(row["match_id"]),
            discord_member_id=int(row["discord_member_id"]),
            elo_at_match=int(row["elo_at_match"]) if row["elo_at_match"] is not None else None,
            roles_selected=tuple(str(value) for value in row["roles_selected"]),
            entry_type=int(row["entry_type"]),
            wait_time_seconds=int(row["wait_time_seconds"]),
        )

    @staticmethod
    async def insert(
        conn: asyncpg.Connection,
        *,
        match_id: int,
        discord_member_id: int,
        elo_at_match: int | None,
        roles_selected: tuple[str, ...],
        entry_type: int,
        wait_time_seconds: int,
    ) -> None:
        await conn.execute(
            """
            INSERT INTO five_stack_match_participants (
              match_id, discord_member_id, elo_at_match, roles_selected,
              entry_type, wait_time_seconds
            )
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (match_id, discord_member_id) DO NOTHING;
            """,
            match_id,
            discord_member_id,
            elo_at_match,
            list(roles_selected),
            entry_type,
            wait_time_seconds,
        )

    @classmethod
    async def list_by_match(cls, conn: asyncpg.Connection, match_id: int) -> list[FiveStackMatchParticipantRow]:
        rows = await conn.fetch(
            """
            SELECT match_id, discord_member_id, elo_at_match, roles_selected,
                   entry_type, wait_time_seconds
              FROM five_stack_match_participants
             WHERE match_id = $1;
            """,
            match_id,
        )
        return [cls._row_to_model(row) for row in rows]

    @classmethod
    async def list_by_member(
        cls,
        conn: asyncpg.Connection,
        *,
        discord_member_id: int,
        limit: int,
    ) -> list[FiveStackMatchParticipantRow]:
        rows = await conn.fetch(
            """
            SELECT match_id, discord_member_id, elo_at_match, roles_selected,
                   entry_type, wait_time_seconds
              FROM five_stack_match_participants
             WHERE discord_member_id = $1
             ORDER BY match_id DESC
             LIMIT $2;
            """,
            discord_member_id,
            limit,
        )
        return [cls._row_to_model(row) for row in rows]
