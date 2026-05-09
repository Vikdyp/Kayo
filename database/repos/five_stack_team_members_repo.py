from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg


@dataclass(frozen=True, slots=True)
class FiveStackTeamMemberRow:
    guild_id: int
    team_code: str
    member_discord_id: int
    joined_at: datetime


class FiveStackTeamMembersRepo:
    @staticmethod
    def _row_to_model(row: asyncpg.Record) -> FiveStackTeamMemberRow:
        return FiveStackTeamMemberRow(
            guild_id=int(row["guild_id"]),
            team_code=str(row["team_code"]),
            member_discord_id=int(row["member_discord_id"]),
            joined_at=row["joined_at"],
        )

    @staticmethod
    async def insert(
        conn: asyncpg.Connection,
        *,
        guild_id: int,
        team_code: str,
        member_discord_id: int,
    ) -> bool:
        row = await conn.fetchrow(
            """
            INSERT INTO five_stack_team_members (guild_id, team_code, member_discord_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id, team_code, member_discord_id) DO NOTHING
            RETURNING member_discord_id;
            """,
            guild_id,
            team_code,
            member_discord_id,
        )
        return row is not None

    @staticmethod
    async def delete(
        conn: asyncpg.Connection,
        *,
        guild_id: int,
        team_code: str,
        member_discord_id: int,
    ) -> bool:
        result = await conn.execute(
            """
            DELETE FROM five_stack_team_members
             WHERE guild_id = $1
               AND team_code = $2
               AND member_discord_id = $3;
            """,
            guild_id,
            team_code,
            member_discord_id,
        )
        return result != "DELETE 0"

    @staticmethod
    async def delete_team(conn: asyncpg.Connection, *, guild_id: int, team_code: str) -> int:
        result = await conn.execute(
            """
            DELETE FROM five_stack_team_members
             WHERE guild_id = $1
               AND team_code = $2;
            """,
            guild_id,
            team_code,
        )
        return int(result.split()[-1])

    @classmethod
    async def list_by_team(
        cls,
        conn: asyncpg.Connection,
        *,
        guild_id: int,
        team_code: str,
    ) -> list[FiveStackTeamMemberRow]:
        rows = await conn.fetch(
            """
            SELECT guild_id, team_code, member_discord_id, joined_at
              FROM five_stack_team_members
             WHERE guild_id = $1
               AND team_code = $2
             ORDER BY joined_at;
            """,
            guild_id,
            team_code,
        )
        return [cls._row_to_model(row) for row in rows]

    @classmethod
    async def get_user_membership(
        cls,
        conn: asyncpg.Connection,
        *,
        guild_id: int,
        member_discord_id: int,
    ) -> FiveStackTeamMemberRow | None:
        row = await conn.fetchrow(
            """
            SELECT guild_id, team_code, member_discord_id, joined_at
              FROM five_stack_team_members
             WHERE guild_id = $1
               AND member_discord_id = $2
             LIMIT 1;
            """,
            guild_id,
            member_discord_id,
        )
        return cls._row_to_model(row) if row else None
