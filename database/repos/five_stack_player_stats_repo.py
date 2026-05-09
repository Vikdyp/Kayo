from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import asyncpg


@dataclass(frozen=True, slots=True)
class FiveStackPlayerStatsRow:
    guild_id: int
    discord_member_id: int
    total_matches: int
    total_wait_time_seconds: int
    matches_as_solo: int
    matches_in_group: int
    last_match_at: Optional[datetime]
    preferred_role: Optional[str]


class FiveStackPlayerStatsRepo:
    @staticmethod
    def _row_to_model(row: asyncpg.Record) -> FiveStackPlayerStatsRow:
        return FiveStackPlayerStatsRow(
            guild_id=int(row["guild_id"]),
            discord_member_id=int(row["discord_member_id"]),
            total_matches=int(row["total_matches"]),
            total_wait_time_seconds=int(row["total_wait_time_seconds"]),
            matches_as_solo=int(row["matches_as_solo"]),
            matches_in_group=int(row["matches_in_group"]),
            last_match_at=row["last_match_at"],
            preferred_role=str(row["preferred_role"]) if row["preferred_role"] else None,
        )

    @staticmethod
    async def upsert_after_match(
        conn: asyncpg.Connection,
        *,
        guild_id: int,
        discord_member_id: int,
        wait_time_seconds: int,
        is_solo: bool,
        preferred_role: str | None,
    ) -> None:
        await conn.execute(
            """
            INSERT INTO five_stack_player_stats (
              guild_id, discord_member_id, total_matches,
              total_wait_time_seconds, matches_as_solo, matches_in_group,
              last_match_at, preferred_role
            )
            VALUES ($1, $2, 1, $3, $4, $5, now(), $6)
            ON CONFLICT (guild_id, discord_member_id) DO UPDATE SET
              total_matches = five_stack_player_stats.total_matches + 1,
              total_wait_time_seconds = five_stack_player_stats.total_wait_time_seconds + EXCLUDED.total_wait_time_seconds,
              matches_as_solo = five_stack_player_stats.matches_as_solo + EXCLUDED.matches_as_solo,
              matches_in_group = five_stack_player_stats.matches_in_group + EXCLUDED.matches_in_group,
              last_match_at = now(),
              preferred_role = COALESCE(EXCLUDED.preferred_role, five_stack_player_stats.preferred_role);
            """,
            guild_id,
            discord_member_id,
            wait_time_seconds,
            1 if is_solo else 0,
            0 if is_solo else 1,
            preferred_role,
        )

    @classmethod
    async def get(
        cls,
        conn: asyncpg.Connection,
        *,
        guild_id: int,
        discord_member_id: int,
    ) -> FiveStackPlayerStatsRow | None:
        row = await conn.fetchrow(
            """
            SELECT guild_id, discord_member_id, total_matches,
                   total_wait_time_seconds, matches_as_solo, matches_in_group,
                   last_match_at, preferred_role
              FROM five_stack_player_stats
             WHERE guild_id = $1
               AND discord_member_id = $2;
            """,
            guild_id,
            discord_member_id,
        )
        return cls._row_to_model(row) if row else None

    @classmethod
    async def leaderboard(
        cls,
        conn: asyncpg.Connection,
        *,
        guild_id: int,
        order_by: str,
        limit: int,
    ) -> list[FiveStackPlayerStatsRow]:
        if order_by == "wait_time":
            order_sql = "total_wait_time_seconds DESC"
        else:
            order_sql = "total_matches DESC"
        rows = await conn.fetch(
            f"""
            SELECT guild_id, discord_member_id, total_matches,
                   total_wait_time_seconds, matches_as_solo, matches_in_group,
                   last_match_at, preferred_role
              FROM five_stack_player_stats
             WHERE guild_id = $1
             ORDER BY {order_sql}
             LIMIT $2;
            """,
            guild_id,
            limit,
        )
        return [cls._row_to_model(row) for row in rows]
