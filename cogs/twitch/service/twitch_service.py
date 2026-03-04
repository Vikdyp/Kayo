# cogs/twitch/service/twitch_service.py

from __future__ import annotations

import logging
from typing import Optional

from cogs.configuration.services.channel_service import ChannelConfigurationService
from database.services.streamer_partners_service import StreamerPartnersService

logger = logging.getLogger(__name__)

CHANNEL_KEY = "twitch"


class StreamerService:
    """Service métier pour les streamers partenaires Twitch."""

    def __init__(
        self,
        streamer_svc: StreamerPartnersService,
        channel_config_svc: ChannelConfigurationService,
    ):
        self._streamer_svc = streamer_svc
        self._channel_svc = channel_config_svc

    async def add_streamer(self, guild_id: int, guild_name: Optional[str], streamer: str) -> None:
        await self._streamer_svc.add(guild_id, guild_name, streamer)

    async def remove_streamer(self, guild_id: int, streamer: str) -> bool:
        return await self._streamer_svc.remove(guild_id, streamer)

    async def list_streamers(self, guild_id: int) -> list[str]:
        return await self._streamer_svc.list_all(guild_id)

    async def get_notify_channel_id(self, guild_id: int) -> Optional[int]:
        return await self._channel_svc.get_one(guild_id, CHANNEL_KEY)
