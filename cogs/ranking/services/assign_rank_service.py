# cogs/ranking/services/assign_rank_service.py
"""
Service métier pour la gestion des rangs Valorant.
Encapsule les accès DB via les services injectés.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

from cogs.configuration.services.channel_service import ChannelConfigurationService
from cogs.configuration.services.role_service import RoleConfigurationService
from database.services.persistent_messages_service import (
    PersistentMessagesService,
    PersistentMessageInfo,
)
from database.services.valorant_info_service import ValorantInfoService

logger = logging.getLogger(__name__)

RANGS_VALORANT = (
    "fer", "bronze", "argent", "or", "platine",
    "diamant", "ascendant", "immortel", "radiant", "no_rank",
)


class AssignRankService:
    """Service métier pour l'assignation de rangs Valorant."""

    def __init__(
        self,
        valorant_info_svc: ValorantInfoService,
        channel_config_svc: ChannelConfigurationService,
        role_config_svc: RoleConfigurationService,
        persistent_msg_svc: PersistentMessagesService,
    ):
        self._valo_svc = valorant_info_svc
        self._channel_svc = channel_config_svc
        self._role_svc = role_config_svc
        self._persistent_msg_svc = persistent_msg_svc
        # Role cache
        self._role_cache: dict[int, dict[str, int]] = {}
        self._role_cache_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Channel config
    # ------------------------------------------------------------------

    async def get_channel_id(self, guild_id: int, key: str) -> Optional[int]:
        return await self._channel_svc.get_one(guild_id, key)

    # ------------------------------------------------------------------
    # Persistent messages
    # ------------------------------------------------------------------

    async def get_persistent_message(
        self, guild_id: int, message_type: str
    ) -> Optional[PersistentMessageInfo]:
        return await self._persistent_msg_svc.get(guild_id, message_type)

    async def store_persistent_message(
        self,
        guild_id: int,
        guild_name: Optional[str],
        channel_id: int,
        message_id: int,
        message_type: str,
    ) -> None:
        await self._persistent_msg_svc.save(
            guild_id, guild_name, message_type, channel_id, message_id
        )

    # ------------------------------------------------------------------
    # Valorant info (delegated to ValorantInfoService)
    # ------------------------------------------------------------------

    async def update_user_valorant_info(self, discord_id: int, pseudo: str, tag: str) -> bool:
        return await self._valo_svc.upsert_pseudo_tag(discord_id, pseudo, tag)

    async def delete_valo_data(self, discord_id: int) -> bool:
        return await self._valo_svc.delete(discord_id)

    async def valorant_account_linked(self, discord_id: int) -> bool:
        return await self._valo_svc.account_linked(discord_id)

    async def get_user_by_pseudo_tag(self, pseudo: str, tag: str) -> Optional[int]:
        return await self._valo_svc.find_by_pseudo_tag(pseudo, tag)

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------

    async def get_users_for_pipeline(self, limit: int = 50) -> list:
        return await self._valo_svc.get_users_for_pipeline(limit)

    async def update_pipeline_success(self, discord_id: int, **kwargs) -> bool:
        return await self._valo_svc.update_pipeline_success(discord_id, **kwargs)

    async def update_pipeline_error(self, discord_id: int) -> bool:
        return await self._valo_svc.update_pipeline_error(discord_id)

    async def reset_user_for_account_change(
        self, discord_id: int, pseudo: str, tag: str
    ) -> bool:
        return await self._valo_svc.reset_for_account_change(discord_id, pseudo, tag)

    async def get_all_valorant_discord_ids(self) -> list[int]:
        return await self._valo_svc.get_all_discord_ids()

    # ------------------------------------------------------------------
    # Activity management
    # ------------------------------------------------------------------

    async def mark_user_inactive(self, discord_id: int) -> bool:
        return await self._valo_svc.mark_inactive(discord_id)

    async def reactivate_user(self, discord_id: int) -> bool:
        return await self._valo_svc.reactivate(discord_id)

    # ------------------------------------------------------------------
    # Notification persistence
    # ------------------------------------------------------------------

    async def get_last_notification(self, discord_id: int) -> Optional[datetime]:
        return await self._valo_svc.get_last_notification(discord_id)

    async def update_last_notification(self, discord_id: int, ts: datetime) -> bool:
        return await self._valo_svc.set_last_notification(discord_id, ts)

    # ------------------------------------------------------------------
    # Role mappings (cached)
    # ------------------------------------------------------------------

    async def get_role_mappings(self, guild_id: int) -> Optional[dict[str, int]]:
        async with self._role_cache_lock:
            if guild_id in self._role_cache:
                return self._role_cache[guild_id]

        all_roles = await self._role_svc.get_all(guild_id)
        if not all_roles:
            return None

        mappings = {k: v for k, v in all_roles.items() if k in RANGS_VALORANT}
        if not mappings:
            return None

        async with self._role_cache_lock:
            self._role_cache[guild_id] = mappings
        return mappings

    async def refresh_role_mappings(self, guild_id: int) -> None:
        async with self._role_cache_lock:
            self._role_cache.pop(guild_id, None)
        await self.get_role_mappings(guild_id)
