# cogs/troll/services/quoicoubeh_service.py

from __future__ import annotations

import logging
from typing import Optional

from cogs.configuration.services.role_service import RoleConfigurationService
from database.services.quoi_responses_service import (
    QuoiResponsesService,
    QuoiLeaderboardEntry,
)

logger = logging.getLogger(__name__)

TOP3_ROLE_KEY = "quoicoubeh_top3"


class QuoicoubehService:
    """Service métier pour le quoicoubeh."""

    def __init__(
        self,
        quoi_svc: QuoiResponsesService,
        role_config_svc: RoleConfigurationService,
    ):
        self._quoi_svc = quoi_svc
        self._role_svc = role_config_svc

    async def record_trigger(self, guild_id: int, guild_name: str | None, discord_user_id: int) -> None:
        await self._quoi_svc.increment(guild_id, guild_name, discord_user_id)

    async def get_leaderboard(self, guild_id: int, limit: int = 10) -> list[QuoiLeaderboardEntry]:
        return await self._quoi_svc.get_top(guild_id, limit)

    async def get_top3_role_id(self, guild_id: int) -> Optional[int]:
        return await self._role_svc.get_one(guild_id, TOP3_ROLE_KEY)
