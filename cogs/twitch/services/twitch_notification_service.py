from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from database.services.guild_channels_service import ChannelConfigurationService
from database.services.twitch_streamers_service import TwitchStreamersDbService

STREAMER_CHANNEL_KEY = "twitch"
STREAMER_LOGIN_PATTERN = re.compile(r"^[a-z0-9_]{3,25}$")

StreamerMutationStatus = Literal["created", "already_exists", "removed", "not_found", "invalid"]


@dataclass(frozen=True, slots=True)
class StreamerMutationResult:
    status: StreamerMutationStatus
    streamer_login: str

    @property
    def changed(self) -> bool:
        return self.status in {"created", "removed"}


class TwitchNotificationService:
    def __init__(
        self,
        streamers_db_service: TwitchStreamersDbService,
        channel_config_service: ChannelConfigurationService,
    ) -> None:
        self._streamers = streamers_db_service
        self._channels = channel_config_service

    async def add_streamer(
        self,
        *,
        guild_id: int,
        guild_name: str | None,
        streamer: str,
    ) -> StreamerMutationResult:
        login = normalize_streamer_login(streamer)
        if login is None:
            return StreamerMutationResult(status="invalid", streamer_login=streamer.strip())

        inserted = await self._streamers.add_streamer(
            guild_id=guild_id,
            guild_name=guild_name,
            streamer_login=login,
        )
        return StreamerMutationResult(
            status="created" if inserted else "already_exists",
            streamer_login=login,
        )

    async def remove_streamer(self, *, guild_id: int, streamer: str) -> StreamerMutationResult:
        login = normalize_streamer_login(streamer)
        if login is None:
            return StreamerMutationResult(status="invalid", streamer_login=streamer.strip())

        removed = await self._streamers.remove_streamer(guild_id=guild_id, streamer_login=login)
        return StreamerMutationResult(
            status="removed" if removed else "not_found",
            streamer_login=login,
        )

    async def list_streamers(self, guild_id: int) -> list[str]:
        return await self._streamers.list_streamers(guild_id)

    async def get_notify_channel_id(self, guild_id: int) -> int | None:
        return await self._channels.get_one(guild_id, STREAMER_CHANNEL_KEY)


def normalize_streamer_login(value: str) -> str | None:
    login = value.strip().removeprefix("@").lower()
    if not STREAMER_LOGIN_PATTERN.fullmatch(login):
        return None
    return login
