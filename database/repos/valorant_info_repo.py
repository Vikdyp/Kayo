# database/repos/valorant_info_repo.py
"""
Repo pour la table valorant_info.
NOTE: utilise encore la table legacy user_id (FK user_id.id).
      Une migration future pourra restructurer vers discord_user_id direct.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import asyncpg


class ValorantInfoRepo:

    # -- Helpers --------------------------------------------------------

    @staticmethod
    async def _get_user_pk(conn: asyncpg.Connection, discord_id: int) -> Optional[int]:
        return await conn.fetchval(
            "SELECT id FROM user_id WHERE discord_id = $1 LIMIT 1;",
            discord_id,
        )

    # -- CRUD -----------------------------------------------------------

    @staticmethod
    async def upsert_pseudo_tag(
        conn: asyncpg.Connection, user_pk: int, pseudo: str, tag: str
    ) -> None:
        await conn.execute(
            """
            INSERT INTO valorant_info (user_id, pseudo, tag, last_notification)
            VALUES ($1, $2, $3, NULL)
            ON CONFLICT (user_id)
            DO UPDATE SET pseudo = EXCLUDED.pseudo,
                          tag    = EXCLUDED.tag,
                          puuid  = NULL,
                          region = NULL,
                          last_notification = NULL;
            """,
            user_pk, pseudo, tag,
        )

    @staticmethod
    async def delete(conn: asyncpg.Connection, user_pk: int) -> None:
        await conn.execute("DELETE FROM valorant_info WHERE user_id = $1;", user_pk)

    @staticmethod
    async def exists(conn: asyncpg.Connection, user_pk: int) -> bool:
        row = await conn.fetchrow(
            "SELECT 1 FROM valorant_info WHERE user_id = $1 LIMIT 1;", user_pk
        )
        return row is not None

    @staticmethod
    async def has_puuid(conn: asyncpg.Connection, user_pk: int) -> bool:
        row = await conn.fetchrow(
            "SELECT puuid FROM valorant_info WHERE user_id = $1 LIMIT 1;", user_pk
        )
        return row is not None and row["puuid"] is not None

    # -- Pipeline queries -----------------------------------------------

    @staticmethod
    async def get_users_for_pipeline(
        conn: asyncpg.Connection, limit: int = 50
    ) -> list[asyncpg.Record]:
        return await conn.fetch(
            """
            SELECT u.discord_id,
                   v.pseudo  AS valorant_pseudo,
                   v.tag     AS valorant_tag,
                   v.puuid   AS valorant_puuid,
                   v.region  AS valorant_region,
                   v.platform AS valorant_platform,
                   v.rank    AS valorant_rank,
                   v.elo     AS valorant_elo,
                   v.error_count,
                   v.last_error_at
              FROM valorant_info v
              JOIN user_id u ON u.id = v.user_id
             WHERE v.is_active = TRUE
               AND v.pseudo IS NOT NULL
               AND v.tag    IS NOT NULL
             ORDER BY v.last_checked_at ASC NULLS FIRST
             LIMIT $1;
            """,
            limit,
        )

    @staticmethod
    async def update_pipeline_success(
        conn: asyncpg.Connection,
        user_pk: int,
        *,
        puuid: Optional[str] = None,
        region: Optional[str] = None,
        platform: Optional[str] = None,
        rank: Optional[str] = None,
        elo: Optional[int] = None,
    ) -> None:
        updates = ["last_checked_at = NOW()", "error_count = 0", "last_error_at = NULL"]
        params: list = []
        idx = 1

        for val, col in [
            (puuid, "puuid"), (region, "region"), (platform, "platform"),
            (rank, "rank"), (elo, "elo"),
        ]:
            if val is not None:
                updates.append(f"{col} = ${idx}")
                params.append(val)
                idx += 1

        params.append(user_pk)
        query = f"UPDATE valorant_info SET {', '.join(updates)} WHERE user_id = ${idx};"
        await conn.execute(query, *params)

    @staticmethod
    async def update_pipeline_error(conn: asyncpg.Connection, user_pk: int) -> None:
        await conn.execute(
            """
            UPDATE valorant_info
               SET error_count = error_count + 1,
                   last_error_at = NOW(),
                   last_checked_at = NOW()
             WHERE user_id = $1;
            """,
            user_pk,
        )

    @staticmethod
    async def reset_for_account_change(
        conn: asyncpg.Connection, user_pk: int, pseudo: str, tag: str
    ) -> None:
        await conn.execute(
            """
            UPDATE valorant_info
               SET pseudo = $1, tag = $2,
                   puuid = NULL, region = NULL, platform = NULL,
                   rank = NULL, elo = NULL,
                   error_count = 0, last_error_at = NULL,
                   last_checked_at = NULL, last_notification = NULL
             WHERE user_id = $3;
            """,
            pseudo, tag, user_pk,
        )

    # -- Activity management --------------------------------------------

    @staticmethod
    async def mark_inactive(conn: asyncpg.Connection, user_pk: int) -> None:
        await conn.execute(
            """
            UPDATE valorant_info
               SET is_active = FALSE, deactivated_at = NOW()
             WHERE user_id = $1 AND is_active = TRUE;
            """,
            user_pk,
        )

    @staticmethod
    async def reactivate(conn: asyncpg.Connection, user_pk: int) -> bool:
        result = await conn.execute(
            """
            UPDATE valorant_info
               SET is_active = TRUE, deactivated_at = NULL,
                   last_checked_at = NULL, error_count = 0
             WHERE user_id = $1 AND is_active = FALSE;
            """,
            user_pk,
        )
        return not result.endswith("0")

    # -- Notification ---------------------------------------------------

    @staticmethod
    async def get_last_notification(conn: asyncpg.Connection, user_pk: int) -> Optional[datetime]:
        return await conn.fetchval(
            "SELECT last_notification FROM valorant_info WHERE user_id = $1;", user_pk
        )

    @staticmethod
    async def set_last_notification(
        conn: asyncpg.Connection, user_pk: int, ts: datetime
    ) -> None:
        await conn.execute(
            "UPDATE valorant_info SET last_notification = $1 WHERE user_id = $2;",
            ts, user_pk,
        )

    # -- Duplicate check ------------------------------------------------

    @staticmethod
    async def find_by_pseudo_tag(
        conn: asyncpg.Connection, pseudo: str, tag: str
    ) -> Optional[int]:
        """Returns discord_id of existing user with this pseudo#tag, or None."""
        return await conn.fetchval(
            """
            SELECT u.discord_id
              FROM valorant_info v
              JOIN user_id u ON v.user_id = u.id
             WHERE v.pseudo = $1 AND v.tag = $2
             LIMIT 1;
            """,
            pseudo, tag,
        )

    # -- All discord_ids (for startup sync) -----------------------------

    @staticmethod
    async def get_all_discord_ids(conn: asyncpg.Connection) -> list[int]:
        rows = await conn.fetch(
            """
            SELECT u.discord_id
              FROM valorant_info v
              JOIN user_id u ON u.id = v.user_id
             WHERE v.pseudo IS NOT NULL AND v.tag IS NOT NULL;
            """
        )
        return [r["discord_id"] for r in rows]

    # -- Tracking -------------------------------------------------------

    @staticmethod
    async def enable_tracking(conn: asyncpg.Connection, user_pk: int) -> None:
        await conn.execute(
            "UPDATE valorant_info SET tracking_enabled = TRUE WHERE user_id = $1;",
            user_pk,
        )

    @staticmethod
    async def disable_tracking(conn: asyncpg.Connection, user_pk: int) -> None:
        await conn.execute(
            "UPDATE valorant_info SET tracking_enabled = FALSE WHERE user_id = $1;",
            user_pk,
        )

    @staticmethod
    async def get_tracking_info(
        conn: asyncpg.Connection, user_pk: int
    ) -> Optional[asyncpg.Record]:
        return await conn.fetchrow(
            "SELECT region, puuid FROM valorant_info WHERE user_id = $1 AND tracking_enabled = TRUE;",
            user_pk,
        )

    # -- Bulk operations ------------------------------------------------

    @staticmethod
    async def bulk_mark_inactive(conn: asyncpg.Connection, discord_ids: list[int]) -> int:
        if not discord_ids:
            return 0
        result = await conn.execute(
            """
            UPDATE valorant_info v
               SET is_active = FALSE, deactivated_at = NOW()
              FROM user_id u
             WHERE u.id = v.user_id
               AND u.discord_id = ANY($1)
               AND v.is_active = TRUE;
            """,
            discord_ids,
        )
        return int(result.split()[-1]) if result.split()[-1].isdigit() else 0
