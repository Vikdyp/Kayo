from __future__ import annotations

from typing import Optional

from database.services.file_counters_service import FileCounterInfo, FileCountersService
from database.services.guild_channels_service import ChannelConfigurationService


FILE_COUNTER_CHANNEL_KEY = "file_counter"


class FileCounterService:
    def __init__(
        self,
        file_counter_db_service: FileCountersService,
        channel_config_service: ChannelConfigurationService,
    ) -> None:
        self._counters = file_counter_db_service
        self._channels = channel_config_service

    async def get_configured_channel_id(self, guild_id: int) -> Optional[int]:
        return await self._channels.get_one(guild_id, FILE_COUNTER_CHANNEL_KEY)

    async def get_counter(self, guild_id: int, channel_id: int) -> Optional[FileCounterInfo]:
        return await self._counters.get_counter(guild_id, channel_id)

    async def list_counters(self) -> list[FileCounterInfo]:
        return await self._counters.list_counters()

    async def reset_counter(
        self,
        *,
        guild_id: int,
        guild_name: str | None,
        channel_id: int,
        message_id: int,
    ) -> FileCounterInfo:
        return await self._counters.reset_counter(
            guild_id=guild_id,
            guild_name=guild_name,
            channel_id=channel_id,
            message_id=message_id,
        )

    async def increment_added(self, *, guild_id: int, channel_id: int) -> Optional[FileCounterInfo]:
        return await self._counters.increment_counter(
            guild_id=guild_id,
            channel_id=channel_id,
            added_delta=1,
        )

    async def increment_completed(self, *, guild_id: int, channel_id: int) -> Optional[FileCounterInfo]:
        return await self._counters.increment_counter(
            guild_id=guild_id,
            channel_id=channel_id,
            completed_delta=1,
        )
