# cogs/role_management/services/role_combination_service.py

from __future__ import annotations

import logging
from typing import Optional

from cogs.configuration.services.channel_service import ChannelConfigurationService
from database.services.role_combinations_service import (
    RoleCombinationsService,
    RoleCombinationInfo,
)

logger = logging.getLogger(__name__)


class RoleCombinationService:
    """Service métier pour les combinaisons de rôles."""

    def __init__(
        self,
        role_combinations_svc: RoleCombinationsService,
        channel_config_svc: ChannelConfigurationService,
    ):
        self._combos_svc = role_combinations_svc
        self._channel_svc = channel_config_svc

    async def get_combinations(self, guild_id: int) -> list[RoleCombinationInfo]:
        return await self._combos_svc.get_all(guild_id)

    async def add_combination(
        self,
        guild_id: int,
        guild_name: Optional[str],
        primary_role_id: int,
        secondary_role_id: int,
        combined_role_id: int,
    ) -> None:
        await self._combos_svc.add(
            guild_id, guild_name, primary_role_id, secondary_role_id, combined_role_id
        )

    async def remove_combination(
        self,
        guild_id: int,
        primary_role_id: int,
        secondary_role_id: int,
    ) -> bool:
        return await self._combos_svc.remove(guild_id, primary_role_id, secondary_role_id)

    async def get_moderation_channel_id(self, guild_id: int) -> Optional[int]:
        return await self._channel_svc.get_one(guild_id, "modération")
