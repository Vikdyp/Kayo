from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal, Optional

import asyncpg

ReputationEventType = Literal["report", "recommendation"]


@dataclass(frozen=True, slots=True)
class ReputationSummaryRow:
    reports: int
    recommendations: int


class ReputationEventsRepo:
    @staticmethod
    async def count_for_pair(
        conn: asyncpg.Connection,
        *,
        guild_id: int,
        reporter_user_id: int,
        target_user_id: int,
        event_type: ReputationEventType,
        event_date: Optional[date] = None,
    ) -> int:
        if event_date is None:
            row = await conn.fetchrow(
                """
                SELECT COALESCE(SUM(count), 0) AS total
                  FROM reputation_events
                 WHERE guild_id = $1
                   AND reporter_user_id = $2
                   AND target_user_id = $3
                   AND event_type = $4;
                """,
                guild_id,
                reporter_user_id,
                target_user_id,
                event_type,
            )
        else:
            row = await conn.fetchrow(
                """
                SELECT COALESCE(SUM(count), 0) AS total
                  FROM reputation_events
                 WHERE guild_id = $1
                   AND reporter_user_id = $2
                   AND target_user_id = $3
                   AND event_type = $4
                   AND event_date = $5;
                """,
                guild_id,
                reporter_user_id,
                target_user_id,
                event_type,
                event_date,
            )
        return int(row["total"])

    @staticmethod
    async def insert_event(
        conn: asyncpg.Connection,
        *,
        guild_id: int,
        reporter_user_id: int,
        target_user_id: int,
        event_type: ReputationEventType,
        reason: str | None,
        event_date: date,
    ) -> bool:
        row = await conn.fetchrow(
            """
            INSERT INTO reputation_events (
              guild_id, reporter_user_id, target_user_id, event_type, reason, event_date
            )
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (guild_id, reporter_user_id, target_user_id, event_type, event_date)
              DO NOTHING
            RETURNING id;
            """,
            guild_id,
            reporter_user_id,
            target_user_id,
            event_type,
            reason,
            event_date,
        )
        return row is not None

    @staticmethod
    async def get_summary(
        conn: asyncpg.Connection,
        *,
        guild_id: int,
        target_user_id: int,
    ) -> ReputationSummaryRow:
        row = await conn.fetchrow(
            """
            SELECT
              COALESCE(SUM(count) FILTER (WHERE event_type = 'report'), 0) AS reports,
              COALESCE(SUM(count) FILTER (WHERE event_type = 'recommendation'), 0) AS recommendations
            FROM reputation_events
            WHERE guild_id = $1
              AND target_user_id = $2;
            """,
            guild_id,
            target_user_id,
        )
        return ReputationSummaryRow(
            reports=int(row["reports"]),
            recommendations=int(row["recommendations"]),
        )
