from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from cogs.tournaments.services import TournamentService


class FakeTournamentsDbService:
    def __init__(self) -> None:
        self.create_kwargs = None
        self.register_kwargs = None

    async def create(self, **kwargs):
        self.create_kwargs = kwargs
        return SimpleNamespace(id=1, tournament_name=kwargs["tournament_name"])

    async def register_team(self, **kwargs):
        self.register_kwargs = kwargs
        return SimpleNamespace(status="created", team=None)

    async def get_active(self, guild_id: int):
        return None

    async def set_registration_message(self, **kwargs):
        return None

    async def close_active(self, guild_id: int) -> bool:
        return True


class FakeChannelsService:
    async def get_one(self, guild_id: int, key: str):
        return {"inscription_tournament_channel_id": 10, "tournament_channel_id": 20}.get(key)


def make_service() -> TournamentService:
    return TournamentService(FakeTournamentsDbService(), FakeChannelsService())


def test_parse_team_registration_requires_exactly_five_players() -> None:
    parsed = TournamentService.parse_team_registration(
        team_name=" Perfect Team ",
        players_raw="1, 2, 3, 4, 5",
        extras_raw="6,7,8",
    )

    assert parsed.team_name == "Perfect Team"
    assert parsed.player_discord_ids == (1, 2, 3, 4, 5)
    assert parsed.substitute_discord_ids == (6, 7)
    assert parsed.coach_discord_id == 8


def test_parse_team_registration_rejects_bad_players() -> None:
    with pytest.raises(ValueError):
        TournamentService.parse_team_registration(
            team_name="Team",
            players_raw="1, 2",
            extras_raw="",
        )


@pytest.mark.asyncio
async def test_create_tournament_rejects_invalid_dates() -> None:
    service = make_service()
    now = datetime(2026, 5, 9, tzinfo=timezone.utc)

    result = await service.create_tournament(
        guild_id=1,
        guild_name="Guild",
        tournament_name="Cup",
        max_teams=8,
        registration_start=now,
        registration_end=datetime(2026, 5, 8, tzinfo=timezone.utc),
        tournament_date=now,
    )

    assert result is None
