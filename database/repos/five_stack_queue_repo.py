from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import asyncpg


@dataclass(frozen=True, slots=True)
class FiveStackQueueRow:
    id: int
    guild_id: int
    discord_member_id: int
    entry_type: int
    team_code: Optional[str]
    team_member_ids: tuple[int, ...]
    language: str
    region: str
    platform: str
    desired_team_size: int
    mmr_extended: bool
    elo: Optional[int]
    elo_high: Optional[int]
    elo_low: Optional[int]
    roles: tuple[str, ...]
    queued_at: datetime

    @property
    def all_member_ids(self) -> tuple[int, ...]:
        return self.team_member_ids or (self.discord_member_id,)


class FiveStackQueueRepo:
    @staticmethod
    def _row_to_model(row: asyncpg.Record) -> FiveStackQueueRow:
        return FiveStackQueueRow(
            id=int(row["id"]),
            guild_id=int(row["guild_id"]),
            discord_member_id=int(row["discord_member_id"]),
            entry_type=int(row["entry_type"]),
            team_code=str(row["team_code"]) if row["team_code"] is not None else None,
            team_member_ids=tuple(int(value) for value in row["team_member_ids"]),
            language=str(row["language"]),
            region=str(row["region"]),
            platform=str(row["platform"]),
            desired_team_size=int(row["desired_team_size"]),
            mmr_extended=bool(row["mmr_extended"]),
            elo=int(row["elo"]) if row["elo"] is not None else None,
            elo_high=int(row["elo_high"]) if row["elo_high"] is not None else None,
            elo_low=int(row["elo_low"]) if row["elo_low"] is not None else None,
            roles=tuple(str(value) for value in row["roles"]),
            queued_at=row["queued_at"],
        )

    @classmethod
    async def upsert(
        cls,
        conn: asyncpg.Connection,
        *,
        guild_id: int,
        discord_member_id: int,
        entry_type: int,
        team_code: str | None,
        team_member_ids: tuple[int, ...],
        language: str,
        region: str,
        platform: str,
        desired_team_size: int,
        mmr_extended: bool,
        elo: int | None,
        elo_high: int | None,
        elo_low: int | None,
        roles: tuple[str, ...],
    ) -> FiveStackQueueRow:
        row = await conn.fetchrow(
            """
            INSERT INTO five_stack_queue (
              guild_id, discord_member_id, entry_type, team_code, team_member_ids,
              language, region, platform, desired_team_size, mmr_extended,
              elo, elo_high, elo_low, roles
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            ON CONFLICT (guild_id, discord_member_id) DO UPDATE SET
              entry_type = EXCLUDED.entry_type,
              team_code = EXCLUDED.team_code,
              team_member_ids = EXCLUDED.team_member_ids,
              language = EXCLUDED.language,
              region = EXCLUDED.region,
              platform = EXCLUDED.platform,
              desired_team_size = EXCLUDED.desired_team_size,
              mmr_extended = EXCLUDED.mmr_extended,
              elo = EXCLUDED.elo,
              elo_high = EXCLUDED.elo_high,
              elo_low = EXCLUDED.elo_low,
              roles = EXCLUDED.roles,
              queued_at = now()
            RETURNING id, guild_id, discord_member_id, entry_type, team_code,
                      team_member_ids, language, region, platform,
                      desired_team_size, mmr_extended, elo, elo_high, elo_low,
                      roles, queued_at;
            """,
            guild_id,
            discord_member_id,
            entry_type,
            team_code,
            list(team_member_ids),
            language,
            region,
            platform,
            desired_team_size,
            mmr_extended,
            elo,
            elo_high,
            elo_low,
            list(roles),
        )
        return cls._row_to_model(row)

    @classmethod
    async def list_by_guild(cls, conn: asyncpg.Connection, guild_id: int) -> list[FiveStackQueueRow]:
        rows = await conn.fetch(
            """
            SELECT id, guild_id, discord_member_id, entry_type, team_code,
                   team_member_ids, language, region, platform,
                   desired_team_size, mmr_extended, elo, elo_high, elo_low,
                   roles, queued_at
              FROM five_stack_queue
             WHERE guild_id = $1
             ORDER BY queued_at, id;
            """,
            guild_id,
        )
        return [cls._row_to_model(row) for row in rows]

    @classmethod
    async def list_all(cls, conn: asyncpg.Connection) -> list[FiveStackQueueRow]:
        rows = await conn.fetch(
            """
            SELECT id, guild_id, discord_member_id, entry_type, team_code,
                   team_member_ids, language, region, platform,
                   desired_team_size, mmr_extended, elo, elo_high, elo_low,
                   roles, queued_at
              FROM five_stack_queue
             ORDER BY guild_id, queued_at, id;
            """
        )
        return [cls._row_to_model(row) for row in rows]

    @staticmethod
    async def delete_member(conn: asyncpg.Connection, *, guild_id: int, discord_member_id: int) -> bool:
        result = await conn.execute(
            """
            DELETE FROM five_stack_queue
             WHERE guild_id = $1
               AND (
                 discord_member_id = $2
                 OR $2 = ANY(team_member_ids)
               );
            """,
            guild_id,
            discord_member_id,
        )
        return result != "DELETE 0"

    @staticmethod
    async def delete_ids(conn: asyncpg.Connection, *, guild_id: int, entry_ids: tuple[int, ...]) -> int:
        if not entry_ids:
            return 0
        result = await conn.execute(
            """
            DELETE FROM five_stack_queue
             WHERE guild_id = $1
               AND id = ANY($2);
            """,
            guild_id,
            list(entry_ids),
        )
        return int(result.split()[-1])

    @staticmethod
    async def convert_old_to_any(conn: asyncpg.Connection, *, older_than_seconds: int) -> int:
        result = await conn.execute(
            """
            UPDATE five_stack_queue
               SET desired_team_size = 0
             WHERE desired_team_size <> 0
               AND queued_at < now() - make_interval(secs => $1);
            """,
            older_than_seconds,
        )
        return int(result.split()[-1])

    @staticmethod
    async def delete_stale(conn: asyncpg.Connection, *, older_than_seconds: int) -> list[int]:
        rows = await conn.fetch(
            """
            DELETE FROM five_stack_queue
             WHERE queued_at < now() - make_interval(secs => $1)
            RETURNING discord_member_id;
            """,
            older_than_seconds,
        )
        return [int(row["discord_member_id"]) for row in rows]
