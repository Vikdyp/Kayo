# database/repos/reputation_repo.py

from __future__ import annotations

from datetime import date
from typing import Optional

import asyncpg


class ReputationRepo:

    @staticmethod
    async def add_event(
        conn: asyncpg.Connection,
        guild_id: int,
        reporter_discord_id: int,
        target_discord_id: int,
        event_type: str,
    ) -> bool:
        """Insert a reputation event for today. Returns False if duplicate."""
        try:
            await conn.execute(
                """
                INSERT INTO reputation_events
                    (guild_id, reporter_discord_id, target_discord_id, event_type, event_date)
                VALUES ($1, $2, $3, $4, CURRENT_DATE)
                """,
                guild_id, reporter_discord_id, target_discord_id, event_type,
            )
            return True
        except asyncpg.UniqueViolationError:
            return False

    @staticmethod
    async def count_total(
        conn: asyncpg.Connection,
        guild_id: int,
        reporter_discord_id: int,
        target_discord_id: int,
        event_type: str,
    ) -> int:
        return await conn.fetchval(
            """
            SELECT COUNT(*)
              FROM reputation_events
             WHERE guild_id = $1
               AND reporter_discord_id = $2
               AND target_discord_id = $3
               AND event_type = $4
            """,
            guild_id, reporter_discord_id, target_discord_id, event_type,
        ) or 0

    @staticmethod
    async def get_counts_for_target(
        conn: asyncpg.Connection,
        guild_id: int,
        target_discord_id: int,
    ) -> dict[str, int]:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (WHERE event_type = 'report') AS reports,
                COUNT(*) FILTER (WHERE event_type = 'recommendation') AS recommendations
              FROM reputation_events
             WHERE guild_id = $1 AND target_discord_id = $2
            """,
            guild_id, target_discord_id,
        )
        return {
            "reports": row["reports"] if row else 0,
            "recommendations": row["recommendations"] if row else 0,
        }
