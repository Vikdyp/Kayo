from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from cogs.ranking.services.valorant_pipeline import (
    PipelineStep,
    UserPipelineState,
    ValorantPipeline,
)
from integrations.exceptions import NetworkError, RateLimitError
from integrations.henrikdev.models import RateLimit


def ns(**kwargs):
    return SimpleNamespace(**kwargs)


def user_state(**overrides):
    values = {
        "discord_id": 123456789,
        "pseudo": "Player",
        "tag": "EUW",
        "puuid": None,
        "region": None,
        "platform": None,
        "rank": None,
        "elo": None,
        "error_count": 0,
        "last_error_at": None,
    }
    values.update(overrides)
    return UserPipelineState(**values)


class FakeHenrikService:
    def __init__(self, *, account=None, matches=None, mmr=None, error=None):
        self.account = account
        self.matches = matches or {}
        self.mmr = mmr
        self.error = error
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    async def get_account_by_name(self, name: str, tag: str):
        self.calls.append(("account", (name, tag)))
        if self.error:
            raise self.error
        return self.account

    async def get_matchlist_by_puuid(
        self,
        region: str,
        platform: str,
        puuid: str,
        *,
        size: int = 1,
    ):
        self.calls.append(("matches", (region, platform, puuid, size)))
        if self.error:
            raise self.error
        return self.matches[platform]

    async def get_mmr_by_puuid(self, region: str, platform: str, puuid: str):
        self.calls.append(("mmr", (region, platform, puuid)))
        if self.error:
            raise self.error
        return self.mmr


@pytest.mark.asyncio
async def test_pipeline_nominal_account_platform_then_rank():
    rate_limit = RateLimit(limit=100, remaining=99, reset_seconds=30)
    service = FakeHenrikService(
        account=(
            ns(status=200, data=ns(puuid="puuid-1", region="eu", name="Player", tag="EUW")),
            rate_limit,
        ),
        matches={
            "pc": (ns(status=200, data=[ns(metadata=ns(matchid="match-1"))]), rate_limit),
        },
        mmr=(
            ns(
                status=200,
                data=ns(
                    account=ns(name="Player", tag="EUW"),
                    current=ns(tier=ns(name="Gold 2"), elo=542),
                    seasonal=[ns(season=ns(short="e8a2"))],
                ),
            ),
            rate_limit,
        ),
    )

    pipeline = ValorantPipeline(service)

    result, returned_rate_limit = await pipeline.execute_step(user_state())
    assert returned_rate_limit is rate_limit
    assert result.success is True
    assert result.step is PipelineStep.ACCOUNT_RESOLUTION
    assert result.puuid == "puuid-1"
    assert result.region == "eu"

    result, _ = await pipeline.execute_step(
        user_state(puuid="puuid-1", region="eu")
    )
    assert result.success is True
    assert result.step is PipelineStep.PLATFORM_DETECTION
    assert result.platform == "pc"

    result, _ = await pipeline.execute_step(
        user_state(puuid="puuid-1", region="eu", platform="pc")
    )
    assert result.success is True
    assert result.step is PipelineStep.RANK_RETRIEVAL
    assert result.rank == "Gold 2"
    assert result.elo == 542
    assert result.current_season == 8
    assert result.current_act == 2


@pytest.mark.asyncio
async def test_pipeline_account_not_found_is_notified_failure():
    rate_limit = RateLimit(limit=100, remaining=99, reset_seconds=30)
    pipeline = ValorantPipeline(
        FakeHenrikService(account=(ns(status=404, data=None), rate_limit))
    )

    result, returned_rate_limit = await pipeline.execute_step(user_state())

    assert returned_rate_limit is rate_limit
    assert result.success is False
    assert result.should_notify_user is True
    assert result.error_message == "Compte introuvable: Player#EUW"


@pytest.mark.asyncio
async def test_pipeline_rate_limit_is_raised():
    pipeline = ValorantPipeline(FakeHenrikService(error=RateLimitError("limited")))

    with pytest.raises(RateLimitError):
        await pipeline.execute_step(user_state())


@pytest.mark.asyncio
async def test_pipeline_network_error_returns_step_failure():
    pipeline = ValorantPipeline(FakeHenrikService(error=NetworkError("downstream")))

    result, returned_rate_limit = await pipeline.execute_step(user_state())

    assert returned_rate_limit is None
    assert result.success is False
    assert result.error_message == "downstream"
    assert result.should_notify_user is False
