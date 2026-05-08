# database/repos/valorant_elo_history_repo.py

import asyncpg
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class EloHistoryRow:
    season: int
    act: int
    user_id: int
    recorded_at: datetime
    elo: int
    is_win: bool


def _row_to_model(row: asyncpg.Record) -> EloHistoryRow:
    return EloHistoryRow(
        season=row["season"],
        act=row["act"],
        user_id=row["user_id"],
        recorded_at=row["recorded_at"],
        elo=row["elo"],
        is_win=row["is_win"],
    )


def _validate_partition_key(season: int, act: int) -> None:
    if not isinstance(season, int) or not isinstance(act, int):
        raise TypeError("season and act must be integers")
    if season < 1 or season > 99 or act < 1 or act > 9:
        raise ValueError(f"Invalid Valorant partition key: season={season}, act={act}")


class ValorantEloHistoryRepo:

    # ---- reads ----

    @staticmethod
    async def get_history(
        conn: asyncpg.Connection,
        user_id: int,
        season: int | None = None,
        act: int | None = None,
    ) -> list[EloHistoryRow]:
        sql = (
            "SELECT season, act, user_id, recorded_at, elo, is_win "
            "  FROM valorant_elo_history_parent "
            " WHERE user_id = $1"
        )
        params: list = [user_id]

        if season is not None and act is not None:
            sql += " AND season = $2 AND act = $3"
            params += [season, act]

        sql += " ORDER BY recorded_at;"
        rows = await conn.fetch(sql, *params)
        return [_row_to_model(r) for r in rows]

    @staticmethod
    async def get_last_row(
        conn: asyncpg.Connection, user_id: int
    ) -> Optional[EloHistoryRow]:
        row = await conn.fetchrow(
            """
            SELECT season, act, user_id, recorded_at, elo, is_win
              FROM valorant_elo_history_parent
             WHERE user_id = $1
             ORDER BY recorded_at DESC
             LIMIT 1;
            """,
            user_id,
        )
        return _row_to_model(row) if row else None

    @staticmethod
    async def get_distinct_partitions(
        conn: asyncpg.Connection, user_id: int
    ) -> list[tuple[int, int]]:
        rows = await conn.fetch(
            """
            SELECT DISTINCT season, act
              FROM valorant_elo_history_parent
             WHERE user_id = $1
             ORDER BY season DESC, act DESC;
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
             LIMIT 1;
            """
        )
        if not row:
            return None
        return row["season"], row["act"]

    # ---- writes ----

    @staticmethod
    async def ensure_partitions(
        conn: asyncpg.Connection, season: int, act: int
    ) -> None:
        _validate_partition_key(season, act)
        season_table = f"valorant_elo_history_season_{season}"
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {season_table}
            PARTITION OF valorant_elo_history_parent
            FOR VALUES IN ({season})
            PARTITION BY LIST (act);
        """)

        act_table = f"{season_table}_act_{act}"
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {act_table}
            PARTITION OF {season_table}
            FOR VALUES IN ({act});
        """)

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
            ON CONFLICT (season, act, user_id, recorded_at) DO NOTHING;
            """,
            season, act, user_id, recorded_at, elo, is_win,
        )
