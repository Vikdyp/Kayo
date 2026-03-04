# cogs/file_counter/services/file_counter_service.py

from __future__ import annotations

import logging
from typing import Optional

from database.services.file_counters_service import FileCountersService, CounterInfo

logger = logging.getLogger(__name__)


class FileCounterService:
    """Service métier pour le suivi des fichiers."""

    def __init__(self, counters_svc: FileCountersService):
        self._counters_svc = counters_svc

    async def get_counter(self, guild_id: int, channel_id: int) -> Optional[CounterInfo]:
        return await self._counters_svc.get(guild_id, channel_id)

    async def create_or_update(
        self, guild_id: int, guild_name: Optional[str], channel_id: int, message_id: int
    ) -> None:
        await self._counters_svc.create_or_update(guild_id, guild_name, channel_id, message_id)

    async def increment(
        self, guild_id: int, channel_id: int, ajouter: bool = False, terminer: bool = False
    ) -> Optional[CounterInfo]:
        return await self._counters_svc.increment(guild_id, channel_id, ajouter, terminer)

    async def reset(self, guild_id: int, channel_id: int, message_id: int) -> None:
        await self._counters_svc.reset(guild_id, channel_id, message_id)
