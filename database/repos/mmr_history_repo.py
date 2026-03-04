# database/repos/mmr_history_repo.py
"""
Repo pour la table partitionnée valorant_elo_history_parent.
Gère les partitions (season/act) et les entrées d'historique ELO.
"""

from __future__ import annotations

import re
import logging
from datetime import date, datetime
from typing import Any, Optional

import asyncpg

logger = logging.getLogger(__name__)


class MmrHistoryRepo:

    # -- Partition management ----------------------------------------------

    @staticmethod
    async def ensure_partitions(
        conn: asyncpg.Connection, season_num: int, act_num: int
    ) -> None:
        season_table = f"valorant_elo_history_season_{season_num}"
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {season_table}
            PARTITION OF valorant_elo_history_parent
            FOR VALUES IN ({season_num})
            PARTITION BY LIST (act);
        """)
        act_table = f"{season_table}_act_{act_num}"
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {act_table}
            PARTITION OF {season_table}
            FOR VALUES IN ({act_num});
        """)

    # -- Insert ------------------------------------------------------------

    @staticmethod
    async def insert_entry(
        conn: asyncpg.Connection,
        season: int,
        act: int,
        user_id: int,
        recorded_at: datetime,
        elo: int,
        is_win: bool,
    ) -> None:
        await conn.execute(
            """
            INSERT INTO valorant_elo_history_parent
                (season, act, user_id, recorded_at, elo, is_win)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (season, act, user_id, recorded_at) DO NOTHING
            """,
            season, act, user_id, recorded_at, elo, is_win,
        )

    # -- Queries -----------------------------------------------------------

    @staticmethod
    async def get_last_row(
        conn: asyncpg.Connection, user_id: int
    ) -> Optional[asyncpg.Record]:
        return await conn.fetchrow(
            """
            SELECT season, act, elo
              FROM valorant_elo_history_parent
             WHERE user_id = $1
             ORDER BY recorded_at DESC
             LIMIT 1
            """,
            user_id,
        )

    @staticmethod
    async def get_history(
        conn: asyncpg.Connection,
        user_id: int,
        season: Optional[int] = None,
        act: Optional[int] = None,
    ) -> list[asyncpg.Record]:
        sql = (
            "SELECT season, act, recorded_at, elo"
            "  FROM valorant_elo_history_parent"
            " WHERE user_id = $1"
        )
        params: list[Any] = [user_id]

        if season is not None and act is not None:
            sql += " AND season = $2 AND act = $3"
            params += [season, act]

        sql += " ORDER BY recorded_at"
        return await conn.fetch(sql, *params)

    @staticmethod
    async def get_distinct_partitions(
        conn: asyncpg.Connection, user_id: int
    ) -> list[tuple[int, int]]:
        rows = await conn.fetch(
            """
            SELECT DISTINCT season, act
              FROM valorant_elo_history_parent
             WHERE user_id = $1
             ORDER BY season DESC, act DESC
            """,
            user_id,
        )
        return [(r["season"], r["act"]) for r in rows]

    @staticmethod
    async def get_latest_partition(
        conn: asyncpg.Connection,
    ) -> Optional[tuple[int, int]]:
        row = await conn.fetchrow(
            """
            SELECT season, act
              FROM valorant_elo_history_parent
             GROUP BY season, act
             ORDER BY season DESC, act DESC
             LIMIT 1
            """
        )
        if not row:
            return None
        return row["season"], row["act"]
