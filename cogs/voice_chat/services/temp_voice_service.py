from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

from database.services.guild_channels_service import ChannelConfigurationService


TEMP_VOCAL_CATEGORY_KEY = "temp_vocal_category"
TEMP_VOCAL_LOBBY_KEY = "temp_vocal_lobby"


class VoiceChannelLike(Protocol):
    id: int
    name: str
    category: object | None
    members: list[object]


@dataclass(frozen=True, slots=True)
class TempVoiceConfig:
    category_id: Optional[int]
    lobby_channel_id: Optional[int]

    @property
    def is_complete(self) -> bool:
        return self.category_id is not None and self.lobby_channel_id is not None


class TempVoiceService:
    """Business rules for temporary voice channel creation and cleanup."""

    def __init__(self, channel_config_service: ChannelConfigurationService) -> None:
        self._channels = channel_config_service

    async def get_config(self, guild_id: int) -> TempVoiceConfig:
        return TempVoiceConfig(
            category_id=await self._channels.get_one(guild_id, TEMP_VOCAL_CATEGORY_KEY),
            lobby_channel_id=await self._channels.get_one(guild_id, TEMP_VOCAL_LOBBY_KEY),
        )

    def build_temp_channel_name(self, display_name: str) -> str:
        return f"Salon de {display_name}"

    def is_lobby_join(self, *, after_channel_id: Optional[int], config: TempVoiceConfig) -> bool:
        return config.lobby_channel_id is not None and after_channel_id == config.lobby_channel_id

    def is_temp_channel(self, channel: VoiceChannelLike | None, *, config: TempVoiceConfig) -> bool:
        if channel is None or not config.is_complete:
            return False
        if channel.id == config.lobby_channel_id:
            return False
        category = getattr(channel, "category", None)
        return category is not None and getattr(category, "id", None) == config.category_id

    def should_schedule_deletion(self, channel: VoiceChannelLike | None, *, config: TempVoiceConfig) -> bool:
        return self.is_temp_channel(channel, config=config) and len(getattr(channel, "members", [])) == 0

    def should_cancel_deletion(self, channel: VoiceChannelLike | None, *, config: TempVoiceConfig) -> bool:
        return self.is_temp_channel(channel, config=config) and len(getattr(channel, "members", [])) > 0
