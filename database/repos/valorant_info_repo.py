# database/repos/valorant_info_repo.py

import asyncpg
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class ValorantInfoRow:
    user_id: int
    pseudo: str | None
    tag: str | None
    puuid: str | None
    region: str | None
    platform: str | None
    rank: str | None
    elo: int | None
    current_season: int | None
    current_act: int | None
    is_active: bool
    tracking_enabled: bool
    error_count: int
    last_error_at: datetime | None
    last_checked_at: datetime | None
    last_notification: datetime | None
    deactivated_at: datetime | None
    mmr_history_backfilled_at: datetime | None
    mmr_history_backfill_attempted_at: datetime | None
    mmr_history_backfill_error: str | None


@dataclass(frozen=True)
class ValorantUserPresenceRow:
    user_id: int
    discord_id: int


def _row_to_model(row: asyncpg.Record) -> ValorantInfoRow:
    return ValorantInfoRow(
        user_id=row["user_id"],
        pseudo=row["pseudo"],
        tag=row["tag"],
        puuid=row["puuid"],
        region=row["region"],
        platform=row["platform"],
        rank=row["rank"],
        elo=row["elo"],
        current_season=row["current_season"],
        current_act=row["current_act"],
        is_active=row["is_active"],
        tracking_enabled=row["tracking_enabled"],
        error_count=row["error_count"],
        last_error_at=row["last_error_at"],
        last_checked_at=row["last_checked_at"],
        last_notification=row["last_notification"],
        deactivated_at=row["deactivated_at"],
        mmr_history_backfilled_at=row["mmr_history_backfilled_at"],
        mmr_history_backfill_attempted_at=row["mmr_history_backfill_attempted_at"],
        mmr_history_backfill_error=row["mmr_history_backfill_error"],
    )


class ValorantInfoRepo:

    # ---- reads ----

    @staticmethod
    async def get_by_user_id(
        conn: asyncpg.Connection, user_id: int
    ) -> Optional[ValorantInfoRow]:
        row = await conn.fetchrow(
            """
            SELECT user_id, pseudo, tag, puuid, region, platform, rank, elo,
                   current_season, current_act, is_active, tracking_enabled,
                   error_count, last_error_at, last_checked_at,
                   last_notification, deactivated_at,
                   mmr_history_backfilled_at,
                   mmr_history_backfill_attempted_at,
                   mmr_history_backfill_error
              FROM valorant_info
             WHERE user_id = $1;
            """,
            user_id,
        )
        return _row_to_model(row) if row else None

    @staticmethod
    async def get_by_pseudo_tag(
        conn: asyncpg.Connection, pseudo: str, tag: str
    ) -> Optional[ValorantInfoRow]:
        row = await conn.fetchrow(
            """
            SELECT user_id, pseudo, tag, puuid, region, platform, rank, elo,
                   current_season, current_act, is_active, tracking_enabled,
                   error_count, last_error_at, last_checked_at,
                   last_notification, deactivated_at,
                   mmr_history_backfilled_at,
                   mmr_history_backfill_attempted_at,
                   mmr_history_backfill_error
              FROM valorant_info
             WHERE pseudo = $1
               AND tag = $2
             LIMIT 1;
            """,
            pseudo, tag,
        )
        return _row_to_model(row) if row else None

    @staticmethod
    async def exists(conn: asyncpg.Connection, user_id: int) -> bool:
        row = await conn.fetchrow(
            "SELECT 1 FROM valorant_info WHERE user_id = $1 LIMIT 1;",
            user_id,
        )
        return row is not None

    @staticmethod
    async def has_puuid(conn: asyncpg.Connection, user_id: int) -> bool:
        row = await conn.fetchrow(
            "SELECT puuid FROM valorant_info WHERE user_id = $1 LIMIT 1;",
            user_id,
        )
        return row is not None and row["puuid"] is not None

    @staticmethod
    async def get_for_pipeline(
        conn: asyncpg.Connection, limit: int
    ) -> list[ValorantInfoRow]:
        rows = await conn.fetch(
            """
            SELECT user_id, pseudo, tag, puuid, region, platform, rank, elo,
                   current_season, current_act, is_active, tracking_enabled,
                   error_count, last_error_at, last_checked_at,
                   last_notification, deactivated_at,
                   mmr_history_backfilled_at,
                   mmr_history_backfill_attempted_at,
                   mmr_history_backfill_error
              FROM valorant_info
             WHERE is_active = TRUE
               AND pseudo IS NOT NULL
               AND tag    IS NOT NULL
               AND (
                 last_checked_at IS NULL
                 OR last_checked_at < NOW() - INTERVAL '15 minutes'
               )
             ORDER BY last_checked_at ASC NULLS FIRST
             LIMIT $1;
            """,
            limit,
        )
        return [_row_to_model(r) for r in rows]

    @staticmethod
    async def get_all_with_pseudo_tag(
        conn: asyncpg.Connection,
    ) -> list[ValorantInfoRow]:
        rows = await conn.fetch(
            """
            SELECT user_id, pseudo, tag, puuid, region, platform, rank, elo,
                   current_season, current_act, is_active, tracking_enabled,
                   error_count, last_error_at, last_checked_at,
                   last_notification, deactivated_at,
                   mmr_history_backfilled_at,
                   mmr_history_backfill_attempted_at,
                   mmr_history_backfill_error
              FROM valorant_info
             WHERE pseudo IS NOT NULL
               AND tag    IS NOT NULL;
            """
        )
        return [_row_to_model(r) for r in rows]

    @staticmethod
    async def get_tracked(
        conn: asyncpg.Connection,
    ) -> list[ValorantInfoRow]:
        rows = await conn.fetch(
            """
            SELECT user_id, pseudo, tag, puuid, region, platform, rank, elo,
                   current_season, current_act, is_active, tracking_enabled,
                   error_count, last_error_at, last_checked_at,
                   last_notification, deactivated_at,
                   mmr_history_backfilled_at,
                   mmr_history_backfill_attempted_at,
                   mmr_history_backfill_error
              FROM valorant_info
             WHERE tracking_enabled = TRUE
               AND is_active = TRUE;
            """
        )
        return [_row_to_model(r) for r in rows]

    @staticmethod
    async def get_last_notification(
        conn: asyncpg.Connection, user_id: int
    ) -> Optional[datetime]:
        row = await conn.fetchrow(
            "SELECT last_notification FROM valorant_info WHERE user_id = $1;",
            user_id,
        )
        return row["last_notification"] if row else None

    @staticmethod
    async def get_stats(conn: asyncpg.Connection) -> dict[str, int]:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE is_active = TRUE) AS active,
                COUNT(*) FILTER (WHERE is_active = FALSE) AS inactive,
                COUNT(*) FILTER (WHERE puuid IS NOT NULL) AS with_puuid,
                COUNT(*) FILTER (WHERE tracking_enabled = TRUE) AS tracking_enabled
            FROM valorant_info;
            """
        )
        if not row:
            return {"total": 0, "active": 0, "inactive": 0, "with_puuid": 0, "tracking_enabled": 0}
        return {
            "total": row["total"] or 0,
            "active": row["active"] or 0,
            "inactive": row["inactive"] or 0,
            "with_puuid": row["with_puuid"] or 0,
            "tracking_enabled": row["tracking_enabled"] or 0,
        }

    # ---- writes ----

    @staticmethod
    async def upsert_pseudo_tag(
        conn: asyncpg.Connection, user_id: int, pseudo: str, tag: str
    ) -> None:
        await conn.execute(
            """
            INSERT INTO valorant_info (user_id, pseudo, tag)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id)
            DO UPDATE SET pseudo = EXCLUDED.pseudo,
                          tag    = EXCLUDED.tag,
                          puuid  = NULL,
                          region = NULL,
                          platform = NULL,
                          rank   = NULL,
                          elo    = NULL,
                          current_season = NULL,
                          current_act    = NULL,
                          error_count    = 0,
                          last_error_at  = NULL,
                          last_checked_at = NULL,
                          last_notification = NULL,
                          mmr_history_backfilled_at = NULL,
                          mmr_history_backfill_attempted_at = NULL,
                          mmr_history_backfill_error = NULL;
            """,
            user_id, pseudo, tag,
        )

    @staticmethod
    async def update_pipeline_success(
        conn: asyncpg.Connection,
        user_id: int,
        *,
        puuid: str | None = None,
        region: str | None = None,
        platform: str | None = None,
        rank: str | None = None,
        elo: int | None = None,
        pseudo: str | None = None,
        tag: str | None = None,
        current_season: int | None = None,
        current_act: int | None = None,
    ) -> None:
        await conn.execute(
            """
            UPDATE valorant_info
               SET last_checked_at = NOW(),
                   error_count = 0,
                   last_error_at = NULL,
                   puuid = COALESCE($1::text, puuid),
                   region = COALESCE($2::text, region),
                   platform = COALESCE($3::text, platform),
                   rank = COALESCE($4::text, rank),
                   elo = COALESCE($5::integer, elo),
                   pseudo = COALESCE($6::text, pseudo),
                   tag = COALESCE($7::text, tag),
                   current_season = COALESCE($8::integer, current_season),
                   current_act = COALESCE($9::integer, current_act)
             WHERE user_id = $10;
            """,
            puuid,
            region,
            platform,
            rank,
            elo,
            pseudo,
            tag,
            current_season,
            current_act,
            user_id,
        )

    @staticmethod
    async def update_pipeline_error(
        conn: asyncpg.Connection, user_id: int
    ) -> None:
        await conn.execute(
            """
            UPDATE valorant_info
               SET error_count = error_count + 1,
                   last_error_at = NOW(),
                   last_checked_at = NOW()
             WHERE user_id = $1;
            """,
            user_id,
        )

    @staticmethod
    async def reset_for_account_change(
        conn: asyncpg.Connection, user_id: int, pseudo: str, tag: str
    ) -> None:
        await conn.execute(
            """
            UPDATE valorant_info
               SET pseudo = $1,
                   tag = $2,
                   puuid = NULL,
                   region = NULL,
                   platform = NULL,
                   rank = NULL,
                   elo = NULL,
                   current_season = NULL,
                   current_act = NULL,
                   error_count = 0,
                   last_error_at = NULL,
                   last_checked_at = NULL,
                   last_notification = NULL,
                   mmr_history_backfilled_at = NULL,
                   mmr_history_backfill_attempted_at = NULL,
                   mmr_history_backfill_error = NULL
             WHERE user_id = $3;
            """,
            pseudo, tag, user_id,
        )

    @staticmethod
    async def delete(conn: asyncpg.Connection, user_id: int) -> bool:
        result = await conn.execute(
            "DELETE FROM valorant_info WHERE user_id = $1;", user_id,
        )
        return result != "DELETE 0"

    @staticmethod
    async def mark_inactive(conn: asyncpg.Connection, user_id: int) -> None:
        await conn.execute(
            """
            UPDATE valorant_info
               SET is_active = FALSE,
                   deactivated_at = NOW()
             WHERE user_id = $1
               AND is_active = TRUE;
            """,
            user_id,
        )

    @staticmethod
    async def mark_active(conn: asyncpg.Connection, user_id: int) -> bool:
        result = await conn.execute(
            """
            UPDATE valorant_info
               SET is_active = TRUE,
                   deactivated_at = NULL,
                   last_checked_at = NULL,
                   error_count = 0
             WHERE user_id = $1
               AND is_active = FALSE;
            """,
            user_id,
        )
        return result != "UPDATE 0"

    @staticmethod
    async def bulk_mark_inactive(
        conn: asyncpg.Connection, user_ids: list[int]
    ) -> int:
        if not user_ids:
            return 0
        result = await conn.execute(
            """
            UPDATE valorant_info
               SET is_active = FALSE,
                   deactivated_at = NOW()
             WHERE user_id = ANY($1)
               AND is_active = TRUE;
            """,
            user_ids,
        )
        # result format: "UPDATE N"
        parts = result.split()
        return int(parts[-1]) if parts[-1].isdigit() else 0

    @staticmethod
    async def bulk_mark_active(
        conn: asyncpg.Connection, user_ids: list[int]
    ) -> int:
        if not user_ids:
            return 0
        result = await conn.execute(
            """
            UPDATE valorant_info
               SET is_active = TRUE,
                   deactivated_at = NULL,
                   last_checked_at = NULL,
                   error_count = 0
             WHERE user_id = ANY($1)
               AND is_active = FALSE;
            """,
            user_ids,
        )
        parts = result.split()
        return int(parts[-1]) if parts[-1].isdigit() else 0

    @staticmethod
    async def get_for_pipeline_with_discord_id(
        conn: asyncpg.Connection, limit: int
    ) -> list:
        return await conn.fetch(
            """
            SELECT vi.user_id, vi.pseudo, vi.tag, vi.puuid, vi.region,
                   vi.platform, vi.rank, vi.elo, vi.error_count,
                   vi.last_error_at, u.discord_id
              FROM valorant_info vi
              JOIN users u ON u.user_id = vi.user_id
             WHERE vi.is_active = TRUE
               AND vi.pseudo IS NOT NULL
               AND vi.tag IS NOT NULL
               AND (
                 vi.last_checked_at IS NULL
                 OR vi.last_checked_at < NOW() - INTERVAL '15 minutes'
               )
             ORDER BY vi.last_checked_at ASC NULLS FIRST
             LIMIT $1;
            """,
            limit,
        )

    @staticmethod
    async def get_all_discord_ids(
        conn: asyncpg.Connection,
    ) -> list[int]:
        rows = await conn.fetch(
            """
            SELECT u.discord_id
              FROM valorant_info vi
              JOIN users u ON u.user_id = vi.user_id
             WHERE vi.pseudo IS NOT NULL
               AND vi.tag IS NOT NULL;
            """
        )
        return [r["discord_id"] for r in rows]

    @staticmethod
    async def get_user_ids_by_discord_ids(
        conn: asyncpg.Connection,
        discord_ids: list[int],
    ) -> list[ValorantUserPresenceRow]:
        if not discord_ids:
            return []
        rows = await conn.fetch(
            """
            SELECT u.user_id, u.discord_id
              FROM users u
              JOIN valorant_info vi ON vi.user_id = u.user_id
             WHERE u.discord_id = ANY($1);
            """,
            discord_ids,
        )
        return [
            ValorantUserPresenceRow(
                user_id=row["user_id"],
                discord_id=row["discord_id"],
            )
            for row in rows
        ]

    @staticmethod
    async def enable_tracking(conn: asyncpg.Connection, user_id: int) -> None:
        await conn.execute(
            "UPDATE valorant_info SET tracking_enabled = TRUE WHERE user_id = $1;",
            user_id,
        )

    @staticmethod
    async def disable_tracking(conn: asyncpg.Connection, user_id: int) -> None:
        await conn.execute(
            "UPDATE valorant_info SET tracking_enabled = FALSE WHERE user_id = $1;",
            user_id,
        )

    @staticmethod
    async def update_last_notification(
        conn: asyncpg.Connection, user_id: int, ts: datetime
    ) -> None:
        await conn.execute(
            "UPDATE valorant_info SET last_notification = $1 WHERE user_id = $2;",
            ts, user_id,
        )

    @staticmethod
    async def mark_mmr_history_backfill_attempt(
        conn: asyncpg.Connection, user_id: int, error: str | None = None
    ) -> None:
        await conn.execute(
            """
            UPDATE valorant_info
               SET mmr_history_backfill_attempted_at = NOW(),
                   mmr_history_backfill_error = $1
             WHERE user_id = $2;
            """,
            error,
            user_id,
        )

    @staticmethod
    async def mark_mmr_history_backfilled(
        conn: asyncpg.Connection, user_id: int
    ) -> None:
        await conn.execute(
            """
            UPDATE valorant_info
               SET mmr_history_backfilled_at = NOW(),
                   mmr_history_backfill_attempted_at = NOW(),
                   mmr_history_backfill_error = NULL
             WHERE user_id = $1;
            """,
            user_id,
        )

    @staticmethod
    async def cleanup_old_inactive(
        conn: asyncpg.Connection, days: int
    ) -> int:
        if days < 30:
            return 0
        result = await conn.execute(
            """
            DELETE FROM valorant_info
             WHERE is_active = FALSE
               AND deactivated_at < NOW() - make_interval(days => $1);
            """,
            days,
        )
        parts = result.split()
        return int(parts[-1]) if parts[-1].isdigit() else 0
