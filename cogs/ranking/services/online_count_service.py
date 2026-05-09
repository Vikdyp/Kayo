from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterable

from cogs.ranking.services.rank_notifications_service import RANK_NAMES


@dataclass(frozen=True, slots=True)
class RankOnlineCountConfig:
    rank_roles: dict[str, int]
    rank_channels: dict[str, int]

    @property
    def configured_ranks(self) -> frozenset[str]:
        return frozenset(self.rank_roles) & frozenset(self.rank_channels)


class ChannelEditRateLimiter:
    def __init__(self, *, max_edits: int = 2, window_seconds: float = 600.0) -> None:
        self._max_edits = max_edits
        self._window_seconds = window_seconds
        self._timestamps_by_channel: dict[int, list[float]] = {}

    def allow(self, channel_id: int, *, now: float | None = None) -> bool:
        current_time = time.time() if now is None else now
        cutoff = current_time - self._window_seconds
        timestamps = [
            timestamp
            for timestamp in self._timestamps_by_channel.get(channel_id, [])
            if timestamp > cutoff
        ]
        if len(timestamps) >= self._max_edits:
            self._timestamps_by_channel[channel_id] = timestamps
            return False

        timestamps.append(current_time)
        self._timestamps_by_channel[channel_id] = timestamps
        return True

    def clear(self) -> None:
        self._timestamps_by_channel.clear()


class RankOnlineCountService:
    def __init__(self, role_config_service, channel_config_service) -> None:
        self._roles = role_config_service
        self._channels = channel_config_service

    async def get_config(self, guild_id: int) -> RankOnlineCountConfig:
        roles = await self._roles.get_all(guild_id)
        channels = await self._channels.get_all(guild_id)
        return RankOnlineCountConfig(
            rank_roles={key: role_id for key, role_id in roles.items() if key in RANK_NAMES},
            rank_channels={key: channel_id for key, channel_id in channels.items() if key in RANK_NAMES},
        )

    def rank_names_for_role_ids(
        self,
        role_ids: Iterable[int],
        config: RankOnlineCountConfig,
    ) -> frozenset[str]:
        role_id_set = set(role_ids)
        return frozenset(rank for rank, role_id in config.rank_roles.items() if role_id in role_id_set)

    @staticmethod
    def channel_name(rank: str, online_count: int) -> str:
        return f"{rank}-{online_count}-en-ligne"

    @staticmethod
    def presence_crossed_online_boundary(before_status, after_status, offline_status) -> bool:
        return (
            before_status == offline_status
            and after_status != offline_status
        ) or (
            before_status != offline_status
            and after_status == offline_status
        )
