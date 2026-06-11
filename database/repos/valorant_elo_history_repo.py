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
    puuid: str | None
    rr_delta: int | None
    match_id: str | None
    source: str


def _row_to_model(row: asyncpg.Record) -> EloHistoryRow:
    return EloHistoryRow(
        season=row["season"],
        act=row["act"],
        user_id=row["user_id"],
        recorded_at=row["recorded_at"],
        elo=row["elo"],
        is_win=row["is_win"],
        puuid=row["puuid"],
        rr_delta=row["rr_delta"],
        match_id=row["match_id"],
        source=row["source"],
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
        puuid: str | None = None,
        legacy_only: bool = False,
    ) -> list[EloHistoryRow]:
        sql = (
            "SELECT season, act, user_id, recorded_at, elo, is_win, "
            "       puuid, rr_delta, match_id, source "
            "  FROM valorant_elo_history_parent "
            " WHERE user_id = $1"
        )
        params: list = [user_id]

        if season is not None and act is not None:
            sql += f" AND season = ${len(params) + 1} AND act = ${len(params) + 2}"
            params += [season, act]

        if puuid is not None:
            sql += f" AND puuid = ${len(params) + 1}"
            params.append(puuid)
        elif legacy_only:
            sql += " AND puuid IS NULL AND source = 'legacy'"

        sql += " ORDER BY recorded_at;"
        rows = await conn.fetch(sql, *params)
        return [_row_to_model(r) for r in rows]

    @staticmethod
    async def get_last_row(
        conn: asyncpg.Connection,
        user_id: int,
        puuid: str | None = None,
        legacy_only: bool = False,
    ) -> Optional[EloHistoryRow]:
        sql = (
            "SELECT season, act, user_id, recorded_at, elo, is_win, "
            "       puuid, rr_delta, match_id, source "
            "  FROM valorant_elo_history_parent "
            " WHERE user_id = $1"
        )
        params: list = [user_id]
        if puuid is not None:
            sql += " AND puuid = $2"
            params.append(puuid)
        elif legacy_only:
            sql += " AND puuid IS NULL AND source = 'legacy'"
        sql += " ORDER BY recorded_at DESC LIMIT 1;"
        row = await conn.fetchrow(sql, *params)
        return _row_to_model(row) if row else None

    @staticmethod
    async def get_distinct_partitions(
        conn: asyncpg.Connection,
        user_id: int,
        puuid: str | None = None,
        legacy_only: bool = False,
    ) -> list[tuple[int, int]]:
        sql = (
            "SELECT DISTINCT season, act "
            "  FROM valorant_elo_history_parent "
            " WHERE user_id = $1"
        )
        params: list = [user_id]
        if puuid is not None:
            sql += " AND puuid = $2"
            params.append(puuid)
        elif legacy_only:
            sql += " AND puuid IS NULL AND source = 'legacy'"
        sql += " ORDER BY season DESC, act DESC;"
        rows = await conn.fetch(sql, *params)
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
        puuid: str | None = None,
        rr_delta: int | None = None,
        match_id: str | None = None,
        source: str = "tracker_snapshot",
    ) -> bool:
        result = await conn.execute(
            """
            INSERT INTO valorant_elo_history_parent
                   (season, act, user_id, recorded_at, elo, is_win,
                    puuid, rr_delta, match_id, source)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (season, act, user_id, recorded_at)
            DO UPDATE SET
                puuid = COALESCE(valorant_elo_history_parent.puuid, EXCLUDED.puuid),
                rr_delta = COALESCE(valorant_elo_history_parent.rr_delta, EXCLUDED.rr_delta),
                match_id = COALESCE(valorant_elo_history_parent.match_id, EXCLUDED.match_id),
                source = CASE
                    WHEN valorant_elo_history_parent.source = 'legacy'
                         AND EXCLUDED.source <> 'legacy'
                    THEN EXCLUDED.source
                    ELSE valorant_elo_history_parent.source
                END;
            """,
            season,
            act,
            user_id,
            recorded_at,
            elo,
            is_win,
            puuid,
            rr_delta,
            match_id,
            source,
        )
        return result != "INSERT 0 0"
