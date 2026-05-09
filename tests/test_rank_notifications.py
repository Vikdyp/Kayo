from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from cogs.ranking.rank_notifications import RankNotificationsCog
from cogs.ranking.presenters.rank_notifications import (
    build_rank_change_message,
    format_top_percentile,
)
from cogs.ranking.services.rank_notifications_service import (
    RANK_UP_CHANNEL_KEY,
    RankNotificationConfig,
    RankNotificationService,
)


class FakeRoles:
    async def get_all(self, guild_id: int) -> dict[str, int]:
        return {
            "fer": 1,
            "bronze": 2,
            "or": 3,
            "ban": 99,
        }


class FakeChannels:
    async def get_one(self, guild_id: int, key: str) -> int | None:
        if key == RANK_UP_CHANNEL_KEY:
            return 42
        return None


def make_service() -> RankNotificationService:
    return RankNotificationService(FakeRoles(), FakeChannels())


@pytest.mark.asyncio
async def test_rank_notification_service_reads_filtered_config() -> None:
    config = await make_service().get_config(123)

    assert config == RankNotificationConfig(rank_roles={"fer": 1, "bronze": 2, "or": 3}, log_channel_id=42)
    assert config.is_complete is True


def test_rank_notification_service_detects_rank_delta() -> None:
    service = make_service()
    config = RankNotificationConfig(rank_roles={"fer": 1, "bronze": 2, "or": 3}, log_channel_id=42)

    delta = service.analyze_role_delta(before_role_ids=[1], after_role_ids=[2], config=config)

    assert delta.removed == frozenset({"fer"})
    assert delta.added == frozenset({"bronze"})


def test_rank_notification_service_calculates_top_percentile() -> None:
    service = make_service()
    config = RankNotificationConfig(rank_roles={"fer": 1, "bronze": 2, "or": 3}, log_channel_id=42)

    percentile = service.calculate_top_percentile(
        guild_member_role_ids=[
            [3],
            [2],
            [1],
            [],
        ],
        new_rank="bronze",
        config=config,
    )

    assert percentile == pytest.approx(66.66666666666667)


def test_rank_notification_presenter_formats_promotion_and_derank() -> None:
    assert format_top_percentile(0.42) == "0,42"
    assert build_rank_change_message(
        member_mention="<@1>",
        old_rank="bronze",
        new_rank="or",
        top_percentile=75,
    ) == "<@1> vient de passer **Or**. Tu fais partie du top 75% des membres !"
    assert build_rank_change_message(
        member_mention="<@1>",
        old_rank="or",
        new_rank="bronze",
        top_percentile=25,
    ) == "<@1> a derank **Bronze**. Force a toi !"


def test_rank_notification_cog_logs_incomplete_config(caplog: pytest.LogCaptureFixture) -> None:
    cog = RankNotificationsCog(SimpleNamespace(), object())
    guild = SimpleNamespace(id=1, name="Guild")
    config = RankNotificationConfig(rank_roles={}, log_channel_id=None)

    with caplog.at_level(logging.WARNING):
        cog._log_incomplete_config(guild, config)

    assert "missing salon `rank_up`, roles de rang" in caplog.text


def test_rank_notification_cog_logs_unmatched_role_update(caplog: pytest.LogCaptureFixture) -> None:
    cog = RankNotificationsCog(SimpleNamespace(), object())
    guild = SimpleNamespace(id=1, name="Guild")
    config = RankNotificationConfig(rank_roles={"bronze": 2}, log_channel_id=42)

    with caplog.at_level(logging.INFO):
        cog._log_unmatched_role_update(guild, {10}, {11}, config)

    assert "changed role ids [10, 11] are not configured rank roles" in caplog.text
