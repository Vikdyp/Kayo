# database/services/valorant_info_service.py
"""
Service DB pour les opérations valorant_info.
Encapsule les accès à la table valorant_info via le repo.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from database.repos.valorant_info_repo import ValorantInfoRepo

logger = logging.getLogger(__name__)


class ValorantInfoService:
    def __init__(self, db):
        self._db = db

    # -- Helper ---------------------------------------------------------

    async def _get_user_pk(self, discord_id: int) -> Optional[int]:
        async with self._db.acquire() as conn:
            return await ValorantInfoRepo._get_user_pk(conn, discord_id)

    # -- CRUD -----------------------------------------------------------

    async def upsert_pseudo_tag(self, discord_id: int, pseudo: str, tag: str) -> bool:
        user_pk = await self._get_user_pk(discord_id)
        if not user_pk:
            return False
        async with self._db.transaction() as conn:
            await ValorantInfoRepo.upsert_pseudo_tag(conn, user_pk, pseudo, tag)
            return True

    async def delete(self, discord_id: int) -> bool:
        user_pk = await self._get_user_pk(discord_id)
        if not user_pk:
            return False
        async with self._db.transaction() as conn:
            await ValorantInfoRepo.delete(conn, user_pk)
            return True

    async def account_linked(self, discord_id: int) -> bool:
        user_pk = await self._get_user_pk(discord_id)
        if not user_pk:
            return False
        async with self._db.acquire() as conn:
            return await ValorantInfoRepo.exists(conn, user_pk)

    # -- Pipeline -------------------------------------------------------

    async def get_users_for_pipeline(self, limit: int = 50) -> list:
        async with self._db.acquire() as conn:
            return await ValorantInfoRepo.get_users_for_pipeline(conn, limit)

    async def update_pipeline_success(
        self, discord_id: int, **kwargs
    ) -> bool:
        user_pk = await self._get_user_pk(discord_id)
        if not user_pk:
            return False
        async with self._db.transaction() as conn:
            await ValorantInfoRepo.update_pipeline_success(conn, user_pk, **kwargs)
            return True

    async def update_pipeline_error(self, discord_id: int) -> bool:
        user_pk = await self._get_user_pk(discord_id)
        if not user_pk:
            return False
        async with self._db.transaction() as conn:
            await ValorantInfoRepo.update_pipeline_error(conn, user_pk)
            return True

    async def reset_for_account_change(
        self, discord_id: int, pseudo: str, tag: str
    ) -> bool:
        user_pk = await self._get_user_pk(discord_id)
        if not user_pk:
            return False
        async with self._db.transaction() as conn:
            await ValorantInfoRepo.reset_for_account_change(conn, user_pk, pseudo, tag)
            return True

    # -- Activity -------------------------------------------------------

    async def mark_inactive(self, discord_id: int) -> bool:
        user_pk = await self._get_user_pk(discord_id)
        if not user_pk:
            return False
        async with self._db.transaction() as conn:
            await ValorantInfoRepo.mark_inactive(conn, user_pk)
            return True

    async def reactivate(self, discord_id: int) -> bool:
        user_pk = await self._get_user_pk(discord_id)
        if not user_pk:
            return False
        async with self._db.transaction() as conn:
            return await ValorantInfoRepo.reactivate(conn, user_pk)

    # -- Notification ---------------------------------------------------

    async def get_last_notification(self, discord_id: int) -> Optional[datetime]:
        user_pk = await self._get_user_pk(discord_id)
        if not user_pk:
            return None
        async with self._db.acquire() as conn:
            return await ValorantInfoRepo.get_last_notification(conn, user_pk)

    async def set_last_notification(self, discord_id: int, ts: datetime) -> bool:
        user_pk = await self._get_user_pk(discord_id)
        if not user_pk:
            return False
        async with self._db.transaction() as conn:
            await ValorantInfoRepo.set_last_notification(conn, user_pk, ts)
            return True

    # -- Duplicate check ------------------------------------------------

    async def find_by_pseudo_tag(self, pseudo: str, tag: str) -> Optional[int]:
        async with self._db.acquire() as conn:
            return await ValorantInfoRepo.find_by_pseudo_tag(conn, pseudo, tag)

    # -- All discord_ids ------------------------------------------------

    async def get_all_discord_ids(self) -> list[int]:
        async with self._db.acquire() as conn:
            return await ValorantInfoRepo.get_all_discord_ids(conn)

    # -- Tracking -------------------------------------------------------

    async def enable_tracking(self, discord_id: int) -> bool:
        user_pk = await self._get_user_pk(discord_id)
        if not user_pk:
            return False
        async with self._db.transaction() as conn:
            await ValorantInfoRepo.enable_tracking(conn, user_pk)
            return True

    async def disable_tracking(self, discord_id: int) -> bool:
        user_pk = await self._get_user_pk(discord_id)
        if not user_pk:
            return False
        async with self._db.transaction() as conn:
            await ValorantInfoRepo.disable_tracking(conn, user_pk)
            return True

    # -- Bulk -----------------------------------------------------------

    async def bulk_mark_inactive(self, discord_ids: list[int]) -> int:
        async with self._db.transaction() as conn:
            return await ValorantInfoRepo.bulk_mark_inactive(conn, discord_ids)
