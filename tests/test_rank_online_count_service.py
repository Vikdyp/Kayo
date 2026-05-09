from __future__ import annotations

import pytest

from cogs.ranking.services.online_count_service import (
    ChannelEditRateLimiter,
    RankOnlineCountService,
)


class FakeConfigService:
    def __init__(self, values: dict[str, int]) -> None:
        self._values = values

    async def get_all(self, guild_id: int) -> dict[str, int]:
        return self._values


@pytest.mark.asyncio
async def test_rank_online_count_config_filters_rank_keys() -> None:
    service = RankOnlineCountService(
        FakeConfigService({"or": 10, "admin": 99}),
        FakeConfigService({"or": 20, "twitch": 88}),
    )

    config = await service.get_config(1)

    assert config.rank_roles == {"or": 10}
    assert config.rank_channels == {"or": 20}
    assert config.configured_ranks == frozenset({"or"})


def test_rank_names_for_role_ids() -> None:
    service = RankOnlineCountService(FakeConfigService({}), FakeConfigService({}))
    config = type(
        "Config",
        (),
        {"rank_roles": {"fer": 1, "or": 2}},
    )()

    assert service.rank_names_for_role_ids([2, 3], config) == frozenset({"or"})


def test_rank_online_count_channel_name_is_discord_safe() -> None:
    assert RankOnlineCountService.channel_name("immortel", 12) == "immortel-12-en-ligne"


def test_presence_crossed_online_boundary() -> None:
    service = RankOnlineCountService(FakeConfigService({}), FakeConfigService({}))

    assert service.presence_crossed_online_boundary("offline", "online", "offline")
    assert service.presence_crossed_online_boundary("online", "offline", "offline")
    assert not service.presence_crossed_online_boundary("idle", "online", "offline")


def test_channel_edit_rate_limiter_allows_two_edits_per_window() -> None:
    limiter = ChannelEditRateLimiter(max_edits=2, window_seconds=10)

    assert limiter.allow(123, now=100)
    assert limiter.allow(123, now=101)
    assert not limiter.allow(123, now=102)
    assert limiter.allow(123, now=111)
