from __future__ import annotations

import pytest

from cogs.reputation.presenters import reputation_ratio
from cogs.reputation.services import (
    BAD_REPUTATION_ROLE_KEY,
    GOOD_REPUTATION_ROLE_KEY,
    ReputationService,
    is_valid_tracker_url,
)
from database.services.reputation_service import ReputationSummary, UserProfileInfo


class FakeReputationDb:
    def __init__(self) -> None:
        self.profile = UserProfileInfo()
        self.saved = None

    async def get_profile(self, discord_id: int) -> UserProfileInfo:
        return self.profile

    async def save_profile(
        self,
        *,
        discord_id: int,
        genre: str | None,
        valorant_tracker: str | None,
        lft: str | None,
        note: str | None,
    ) -> UserProfileInfo:
        self.saved = {
            "discord_id": discord_id,
            "genre": genre,
            "valorant_tracker": valorant_tracker,
            "lft": lft,
            "note": note,
        }
        self.profile = UserProfileInfo(
            genre=genre,
            valorant_tracker=valorant_tracker,
            lft=lft,
            note=note,
        )
        return self.profile


class FakeRoleConfig:
    async def get_all(self, guild_id: int):
        return {
            GOOD_REPUTATION_ROLE_KEY: 10,
            BAD_REPUTATION_ROLE_KEY: 11,
            "ban": 99,
        }


def make_service(db: FakeReputationDb | None = None) -> ReputationService:
    return ReputationService(db or FakeReputationDb(), FakeRoleConfig())


def test_reputation_ratio_is_smoothed() -> None:
    assert reputation_ratio(ReputationSummary(reports=0, recommendations=0)) == 1
    assert reputation_ratio(ReputationSummary(reports=1, recommendations=3)) == 2


def test_reputation_role_plan_adds_good_role_when_ratio_is_positive() -> None:
    service = make_service()

    plan = service.build_reputation_role_plan(
        current_role_ids={11, 99},
        configured_role_ids={GOOD_REPUTATION_ROLE_KEY: 10, BAD_REPUTATION_ROLE_KEY: 11},
        summary=ReputationSummary(reports=0, recommendations=2),
    )

    assert plan.role_id_to_add == 10
    assert plan.role_ids_to_remove == (11,)


def test_reputation_role_plan_adds_bad_role_when_ratio_is_negative() -> None:
    service = make_service()

    plan = service.build_reputation_role_plan(
        current_role_ids={10, 99},
        configured_role_ids={GOOD_REPUTATION_ROLE_KEY: 10, BAD_REPUTATION_ROLE_KEY: 11},
        summary=ReputationSummary(reports=3, recommendations=0),
    )

    assert plan.role_id_to_add == 11
    assert plan.role_ids_to_remove == (10,)


@pytest.mark.parametrize(
    "url",
    [
        "https://tracker.gg/valorant/profile/riot/Curs4d%232908",
        "https://tracker.gg/valorant/profile/riot/Curs4d%232908/overview",
    ],
)
def test_tracker_url_accepts_profile_and_overview_links(url: str) -> None:
    assert is_valid_tracker_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "http://tracker.gg/valorant/profile/riot/Curs4d%232908",
        "https://example.com/valorant/profile/riot/Curs4d%232908",
        "https://tracker.gg/valorant/profile/riot/Curs4d%232908/matches",
    ],
)
def test_tracker_url_rejects_untrusted_or_unexpected_links(url: str) -> None:
    assert is_valid_tracker_url(url) is False


@pytest.mark.asyncio
async def test_reputation_service_validates_profile_fields() -> None:
    service = make_service()

    invalid_genre = await service.save_profile(
        discord_id=1,
        genre="robot",
        valorant_tracker=None,
        lft=None,
        note=None,
    )
    invalid_tracker = await service.save_profile(
        discord_id=1,
        genre="homme",
        valorant_tracker="https://example.com",
        lft=None,
        note=None,
    )
    invalid_note = await service.save_profile(
        discord_id=1,
        genre="homme",
        valorant_tracker=None,
        lft=None,
        note="go https://example.com",
    )

    assert invalid_genre.success is False
    assert invalid_tracker.success is False
    assert invalid_note.success is False


@pytest.mark.asyncio
async def test_reputation_service_merges_and_saves_profile() -> None:
    db = FakeReputationDb()
    db.profile = UserProfileInfo(genre="Homme", valorant_tracker=None, lft="Rien", note="Ancienne")
    service = make_service(db)

    result = await service.save_profile(
        discord_id=1,
        genre=None,
        valorant_tracker="https://tracker.gg/valorant/profile/riot/Name%23TAG/overview",
        lft="LFT",
        note=None,
    )

    assert result.success is True
    assert db.saved == {
        "discord_id": 1,
        "genre": "Homme",
        "valorant_tracker": "https://tracker.gg/valorant/profile/riot/Name%23TAG/overview",
        "lft": "LFT",
        "note": "Ancienne",
    }
