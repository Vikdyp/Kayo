# database/services/valorant_db_service.py
"""
Service DB pour le domaine Valorant.
Orchestre ValorantInfoRepo, ValorantEloHistoryRepo et UserRepo.
Toutes les methodes publiques acceptent discord_id et font le mapping interne.
"""

import logging
from datetime import datetime
from typing import Optional

from database.engine import Db
from database.repos.user_repo import UserRepo
from database.repos.valorant_info_repo import ValorantInfoRepo, ValorantInfoRow
from database.repos.valorant_elo_history_repo import ValorantEloHistoryRepo, EloHistoryRow

logger = logging.getLogger(__name__)


class ValorantDbService:

    def __init__(self, db: Db) -> None:
        self._db = db

    # ==================== helpers ====================

    async def _resolve_user_id(self, conn, discord_id: int) -> Optional[int]:
        return await UserRepo.get_user_id(conn, discord_id)

    async def _require_user_id(self, conn, discord_id: int) -> int:
        uid = await UserRepo.get_user_id(conn, discord_id)
        if uid is None:
            raise ValueError(f"No internal user_id for discord_id={discord_id}")
        return uid

    # ==================== compte ====================

    async def link_account(self, discord_id: int, pseudo: str, tag: str) -> bool:
        async with self._db.transaction() as conn:
            user_id = await UserRepo.ensure_exists(conn, discord_id=discord_id)
            await ValorantInfoRepo.upsert_pseudo_tag(conn, user_id, pseudo, tag)
        return True

    async def delete_account(self, discord_id: int) -> bool:
        async with self._db.transaction() as conn:
            user_id = await self._resolve_user_id(conn, discord_id)
            if user_id is None:
                return False
            return await ValorantInfoRepo.delete(conn, user_id)

    async def account_exists(self, discord_id: int) -> bool:
        async with self._db.acquire() as conn:
            user_id = await self._resolve_user_id(conn, discord_id)
            if user_id is None:
                return False
            return await ValorantInfoRepo.exists(conn, user_id)

    async def has_puuid(self, discord_id: int) -> bool:
        async with self._db.acquire() as conn:
            user_id = await self._resolve_user_id(conn, discord_id)
            if user_id is None:
                return False
            return await ValorantInfoRepo.has_puuid(conn, user_id)

    async def get_by_pseudo_tag(self, pseudo: str, tag: str) -> Optional[int]:
        """Retourne le discord_id associe a ce pseudo#tag, ou None."""
        async with self._db.acquire() as conn:
            row = await ValorantInfoRepo.get_by_pseudo_tag(conn, pseudo, tag)
            if row is None:
                return None
            user_row = await UserRepo.get_by_user_id(conn, row.user_id)
            return user_row.discord_id if user_row else None

    async def reset_for_account_change(
        self, discord_id: int, pseudo: str, tag: str
    ) -> bool:
        async with self._db.transaction() as conn:
            user_id = await self._resolve_user_id(conn, discord_id)
            if user_id is None:
                return False
            await ValorantInfoRepo.reset_for_account_change(conn, user_id, pseudo, tag)
        return True

    # ==================== pipeline ====================

    async def get_users_for_pipeline(self, limit: int = 50) -> list[dict]:
        """Retourne les utilisateurs pour le pipeline avec discord_id (single JOIN)."""
        async with self._db.acquire() as conn:
            rows = await ValorantInfoRepo.get_for_pipeline_with_discord_id(conn, limit)
            return [
                {
                    "discord_id": r["discord_id"],
                    "valorant_pseudo": r["pseudo"],
                    "valorant_tag": r["tag"],
                    "valorant_puuid": r["puuid"],
                    "valorant_region": r["region"],
                    "valorant_platform": r["platform"],
                    "valorant_rank": r["rank"],
                    "valorant_elo": r["elo"],
                    "error_count": r["error_count"],
                    "last_error_at": r["last_error_at"],
                }
                for r in rows
            ]

    async def update_pipeline_success(
        self,
        discord_id: int,
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
    ) -> bool:
        async with self._db.transaction() as conn:
            user_id = await self._resolve_user_id(conn, discord_id)
            if user_id is None:
                return False
            await ValorantInfoRepo.update_pipeline_success(
                conn, user_id,
                puuid=puuid, region=region, platform=platform,
                rank=rank, elo=elo, pseudo=pseudo, tag=tag,
                current_season=current_season, current_act=current_act,
            )
        return True

    async def update_pipeline_error(self, discord_id: int) -> bool:
        async with self._db.transaction() as conn:
            user_id = await self._resolve_user_id(conn, discord_id)
            if user_id is None:
                return False
            await ValorantInfoRepo.update_pipeline_error(conn, user_id)
        return True

    # ==================== activite ====================

    async def mark_inactive(self, discord_id: int) -> bool:
        async with self._db.transaction() as conn:
            user_id = await self._resolve_user_id(conn, discord_id)
            if user_id is None:
                return False
            await ValorantInfoRepo.mark_inactive(conn, user_id)
        return True

    async def reactivate(self, discord_id: int) -> bool:
        async with self._db.transaction() as conn:
            user_id = await self._resolve_user_id(conn, discord_id)
            if user_id is None:
                return False
            return await ValorantInfoRepo.mark_active(conn, user_id)

    async def get_all_discord_ids(self) -> list[int]:
        """Retourne tous les discord_ids avec un compte Valorant lie (single JOIN)."""
        async with self._db.acquire() as conn:
            return await ValorantInfoRepo.get_all_discord_ids(conn)

    async def sync_presence(
        self,
        active_discord_ids: set[int],
        all_discord_ids: set[int],
    ) -> tuple[int, int]:
        """
        Reactive les presents et desactive les absents en une seule transaction.
        Retourne (reactivated, deactivated).
        """
        async with self._db.transaction() as conn:
            rows = await ValorantInfoRepo.get_user_ids_by_discord_ids(
                conn, list(all_discord_ids)
            )
            present_user_ids = [
                r.user_id for r in rows
                if r.discord_id in active_discord_ids
            ]
            absent_user_ids = [
                r.user_id for r in rows
                if r.discord_id not in active_discord_ids
            ]

            reactivated = await ValorantInfoRepo.bulk_mark_active(conn, present_user_ids)
            deactivated = await ValorantInfoRepo.bulk_mark_inactive(conn, absent_user_ids)
        return reactivated, deactivated

    # ==================== notification ====================

    async def get_last_notification(self, discord_id: int) -> Optional[datetime]:
        async with self._db.acquire() as conn:
            user_id = await self._resolve_user_id(conn, discord_id)
            if user_id is None:
                return None
            return await ValorantInfoRepo.get_last_notification(conn, user_id)

    async def update_last_notification(
        self, discord_id: int, ts: datetime
    ) -> bool:
        async with self._db.transaction() as conn:
            user_id = await self._resolve_user_id(conn, discord_id)
            if user_id is None:
                return False
            await ValorantInfoRepo.update_last_notification(conn, user_id, ts)
        return True

    # ==================== MMR tracking ====================

    async def enable_tracking(self, discord_id: int) -> None:
        async with self._db.transaction() as conn:
            user_id = await self._require_user_id(conn, discord_id)
            await ValorantInfoRepo.enable_tracking(conn, user_id)

    async def disable_tracking(self, discord_id: int) -> None:
        async with self._db.transaction() as conn:
            user_id = await self._require_user_id(conn, discord_id)
            await ValorantInfoRepo.disable_tracking(conn, user_id)

    async def get_tracked_players(self) -> list[dict]:
        """Retourne user_id, elo, current_season, current_act pour chaque joueur suivi."""
        async with self._db.acquire() as conn:
            rows = await ValorantInfoRepo.get_tracked(conn)
            return [
                {
                    "user_id": r.user_id,
                    "elo": r.elo,
                    "current_season": r.current_season,
                    "current_act": r.current_act,
                }
                for r in rows
            ]

    async def get_last_history_row(self, user_id: int) -> Optional[EloHistoryRow]:
        async with self._db.acquire() as conn:
            return await ValorantEloHistoryRepo.get_last_row(conn, user_id)

    async def get_history(
        self, discord_id: int, season: int | None = None, act: int | None = None
    ) -> list[EloHistoryRow]:
        async with self._db.acquire() as conn:
            user_id = await self._resolve_user_id(conn, discord_id)
            if user_id is None:
                return []
            return await ValorantEloHistoryRepo.get_history(conn, user_id, season, act)

    async def get_partitions(self, discord_id: int) -> list[tuple[int, int]]:
        async with self._db.acquire() as conn:
            user_id = await self._resolve_user_id(conn, discord_id)
            if user_id is None:
                return []
            return await ValorantEloHistoryRepo.get_distinct_partitions(conn, user_id)

    async def get_latest_partition(self) -> Optional[tuple[int, int]]:
        async with self._db.acquire() as conn:
            return await ValorantEloHistoryRepo.get_latest_partition(conn)

    async def ensure_partitions(self, season: int, act: int) -> None:
        async with self._db.transaction() as conn:
            await ValorantEloHistoryRepo.ensure_partitions(conn, season, act)

    async def insert_history_entry(
        self,
        user_id: int,
        season: int,
        act: int,
        recorded_at: datetime,
        elo: int,
        is_win: bool,
    ) -> None:
        async with self._db.transaction() as conn:
            await ValorantEloHistoryRepo.insert_entry(
                conn, season, act, user_id, recorded_at, elo, is_win,
            )

    async def get_valorant_info_by_user_id(
        self, user_id: int
    ) -> Optional[ValorantInfoRow]:
        async with self._db.acquire() as conn:
            return await ValorantInfoRepo.get_by_user_id(conn, user_id)

    async def get_valorant_info_by_discord_id(
        self, discord_id: int
    ) -> Optional[ValorantInfoRow]:
        async with self._db.acquire() as conn:
            user_id = await self._resolve_user_id(conn, discord_id)
            if user_id is None:
                return None
            return await ValorantInfoRepo.get_by_user_id(conn, user_id)

    # ==================== stats ====================

    async def get_user_stats(self) -> dict[str, int]:
        async with self._db.acquire() as conn:
            return await ValorantInfoRepo.get_stats(conn)

    async def cleanup_old_inactive(self, days: int = 180) -> int:
        async with self._db.transaction() as conn:
            return await ValorantInfoRepo.cleanup_old_inactive(conn, days)
