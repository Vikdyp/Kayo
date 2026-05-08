# database/repos/member_daily_stats_repo.py
"""
SQL pur pour la table member_daily_stats.
Un repo = une table. Aucun appel à un autre repo.
"""

import asyncpg
from datetime import date
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class MemberDailyStatsRow:
    guild_id: int
    date: date
    join_count: int
    leave_count: int


class MemberDailyStatsRepo:

    @staticmethod
    async def get(
        conn: asyncpg.Connection,
        guild_id: int,
        stats_date: date,
    ) -> Optional[MemberDailyStatsRow]:
        """Récupère les stats pour une date donnée."""
        r = await conn.fetchrow(
            """
            SELECT guild_id, date, join_count, leave_count
            FROM member_daily_stats
            WHERE guild_id = $1 AND date = $2;
            """,
            guild_id,
            stats_date,
        )
        if not r:
            return None
        return MemberDailyStatsRow(
            guild_id=r["guild_id"],
            date=r["date"],
            join_count=r["join_count"],
            leave_count=r["leave_count"],
        )

    @staticmethod
    async def increment_join(
        conn: asyncpg.Connection,
        guild_id: int,
        stats_date: date,
    ) -> None:
        """Incrémente le compteur de joins pour la date (upsert atomique)."""
        await conn.execute(
            """
            INSERT INTO member_daily_stats (guild_id, date, join_count, leave_count)
            VALUES ($1, $2, 1, 0)
            ON CONFLICT (guild_id, date) DO UPDATE
                SET join_count = member_daily_stats.join_count + 1,
                    updated_at = now();
            """,
            guild_id,
            stats_date,
        )

    @staticmethod
    async def increment_leave(
        conn: asyncpg.Connection,
        guild_id: int,
        stats_date: date,
    ) -> None:
        """Incrémente le compteur de départs pour la date (upsert atomique)."""
        await conn.execute(
            """
            INSERT INTO member_daily_stats (guild_id, date, join_count, leave_count)
            VALUES ($1, $2, 0, 1)
            ON CONFLICT (guild_id, date) DO UPDATE
                SET leave_count = member_daily_stats.leave_count + 1,
                    updated_at = now();
            """,
            guild_id,
            stats_date,
        )

    @staticmethod
    async def list_range(
        conn: asyncpg.Connection,
        guild_id: int,
        from_date: Optional[date],
        to_date: date,
    ) -> list[MemberDailyStatsRow]:
        """
        Liste les stats dans un intervalle de dates.
        Si from_date est None, récupère tout l'historique jusqu'à to_date.
        """
        if from_date is None:
            rows = await conn.fetch(
                """
                SELECT guild_id, date, join_count, leave_count
                FROM member_daily_stats
                WHERE guild_id = $1 AND date <= $2
                ORDER BY date ASC;
                """,
                guild_id,
                to_date,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT guild_id, date, join_count, leave_count
                FROM member_daily_stats
                WHERE guild_id = $1 AND date >= $2 AND date <= $3
                ORDER BY date ASC;
                """,
                guild_id,
                from_date,
                to_date,
            )
        return [
            MemberDailyStatsRow(
                guild_id=r["guild_id"],
                date=r["date"],
                join_count=r["join_count"],
                leave_count=r["leave_count"],
            )
            for r in rows
        ]

    @staticmethod
    async def sum_range(
        conn: asyncpg.Connection,
        guild_id: int,
        from_date: Optional[date],
        to_date: date,
    ) -> tuple[int, int]:
        """
        Retourne (total_joins, total_leaves) pour l'intervalle.
        Si from_date est None, calcule sur tout l'historique.
        """
        if from_date is None:
            r = await conn.fetchrow(
                """
                SELECT COALESCE(SUM(join_count), 0) AS total_joins,
                       COALESCE(SUM(leave_count), 0) AS total_leaves
                FROM member_daily_stats
                WHERE guild_id = $1 AND date <= $2;
                """,
                guild_id,
                to_date,
            )
        else:
            r = await conn.fetchrow(
                """
                SELECT COALESCE(SUM(join_count), 0) AS total_joins,
                       COALESCE(SUM(leave_count), 0) AS total_leaves
                FROM member_daily_stats
                WHERE guild_id = $1 AND date >= $2 AND date <= $3;
                """,
                guild_id,
                from_date,
                to_date,
            )
        return (int(r["total_joins"]), int(r["total_leaves"]))
