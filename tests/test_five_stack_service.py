from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from cogs.five_stack.services import FiveStackService
from database.repos.five_stack_teams_repo import FiveStackTeamRow
from database.services.five_stack_service import FiveStackTeamInfo


class FakeFiveStackDb:
    def __init__(self) -> None:
        self.teams: dict[str, FiveStackTeamInfo] = {}
        self.queue: list[object] = []
        self.saved_entries: list[dict] = []

    async def get_user_team(self, *, guild_id: int, discord_member_id: int):
        for team in self.teams.values():
            if team.team.guild_id == guild_id and discord_member_id in team.member_ids:
                return team
        return None

    async def get_team(self, *, guild_id: int, code: str):
        team = self.teams.get(code.upper())
        if team and team.team.guild_id == guild_id:
            return team
        return None

    async def create_team(self, *, guild_id: int, guild_name: str | None, code: str, leader_discord_id: int, visibility: str):
        row = FiveStackTeamRow(
            code=code,
            guild_id=guild_id,
            leader_discord_id=leader_discord_id,
            visibility=visibility,
            forum_channel_id=None,
            thread_id=None,
            voice_channel_id=None,
            status="active",
            created_at=datetime.now(timezone.utc),
        )
        team = FiveStackTeamInfo(team=row, member_ids=(leader_discord_id,))
        self.teams[code] = team
        return team

    async def add_team_member(self, *, guild_id: int, guild_name: str | None, code: str, discord_member_id: int):
        team = self.teams[code.upper()]
        updated = FiveStackTeamInfo(team=team.team, member_ids=team.member_ids + (discord_member_id,))
        self.teams[code.upper()] = updated
        return updated

    async def add_queue_entry(self, **kwargs):
        self.saved_entries.append(kwargs)
        return kwargs

    async def list_queue(self, guild_id: int | None = None):
        return tuple(entry for entry in self.queue if guild_id is None or entry.guild_id == guild_id)


class FakeChannels:
    async def get_one(self, guild_id: int, key: str):
        return None


class FakeRoles:
    def __init__(self, roles: dict[str, int]) -> None:
        self.roles = roles

    async def get_all(self, guild_id: int):
        return self.roles


class FakeMessages:
    async def save(self, *args, **kwargs):
        return None

    async def get(self, *args, **kwargs):
        return None


class FakeValorant:
    def __init__(self, profiles: dict[int, object]) -> None:
        self.profiles = profiles

    async def get_valorant_info_by_discord_id(self, discord_id: int):
        return self.profiles.get(discord_id)


@dataclass(frozen=True, slots=True)
class QueueEntry:
    id: int
    guild_id: int
    discord_member_id: int
    entry_type: int
    team_member_ids: tuple[int, ...]
    language: str = "francais"
    region: str = "eu"
    platform: str = "pc"
    desired_team_size: int = 5
    elo: int | None = 1000
    roles: tuple[str, ...] = ("fill",)
    queued_at: datetime = datetime(2026, 1, 1, tzinfo=timezone.utc)

    @property
    def all_member_ids(self) -> tuple[int, ...]:
        return self.team_member_ids or (self.discord_member_id,)


def make_service(*, profiles: dict[int, object] | None = None, roles: dict[str, int] | None = None):
    db = FakeFiveStackDb()
    service = FiveStackService(
        db,
        FakeChannels(),
        FakeRoles(roles or {}),
        FakeMessages(),
        FakeValorant(profiles or {}),
    )
    return service, db


def profile(*, elo: int = 1200, region: str = "eu", platform: str = "pc"):
    return SimpleNamespace(elo=elo, region=region, platform=platform, rank="Gold")


@pytest.mark.asyncio
async def test_build_solo_queue_data_uses_valorant_and_member_roles():
    service, db = make_service(
        profiles={10: profile(elo=1337)},
        roles={"francais": 1, "duelist": 2, "controller": 3},
    )

    data = await service.build_solo_queue_data(
        guild_id=123,
        guild_name="Guild",
        member_id=10,
        role_ids={1, 2},
        desired_team_size=5,
    )

    assert data is not None
    assert data.language == "francais"
    assert data.roles == ("duelist",)
    assert data.elo == 1337

    await service.add_queue_entry(data)
    assert db.saved_entries[0]["guild_id"] == 123
    assert db.saved_entries[0]["team_member_ids"] == (10,)


@pytest.mark.asyncio
async def test_team_create_and_join_require_valorant_profile():
    service, _ = make_service(profiles={1: profile(), 2: profile()})

    created = await service.create_team(
        guild_id=123,
        guild_name="Guild",
        leader_discord_id=1,
        visibility="public",
    )
    assert created.status == "created"
    assert created.team is not None

    joined = await service.join_team(
        guild_id=123,
        guild_name="Guild",
        code=created.team.team.code,
        discord_member_id=2,
    )
    assert joined.status == "joined"
    assert joined.team is not None
    assert joined.team.member_ids == (1, 2)

    missing = await service.join_team(
        guild_id=123,
        guild_name="Guild",
        code=created.team.team.code,
        discord_member_id=3,
    )
    assert missing.status == "missing_valorant"


@pytest.mark.asyncio
async def test_find_match_proposals_groups_compatible_entries():
    service, db = make_service()
    db.queue = [
        QueueEntry(id=1, guild_id=1, discord_member_id=10, entry_type=1, team_member_ids=(10,), roles=("duelist",)),
        QueueEntry(id=2, guild_id=1, discord_member_id=11, entry_type=1, team_member_ids=(11,), roles=("controller",)),
        QueueEntry(id=3, guild_id=1, discord_member_id=12, entry_type=1, team_member_ids=(12,), roles=("sentinel",)),
        QueueEntry(id=4, guild_id=1, discord_member_id=13, entry_type=1, team_member_ids=(13,), roles=("initiator",)),
        QueueEntry(id=5, guild_id=1, discord_member_id=14, entry_type=1, team_member_ids=(14,), roles=("fill",)),
        QueueEntry(id=6, guild_id=1, discord_member_id=20, entry_type=1, team_member_ids=(20,), language="anglais"),
    ]

    proposals = await service.find_match_proposals(guild_id=1)

    assert len(proposals) == 1
    assert proposals[0].member_ids == (10, 11, 12, 13, 14)
    assert proposals[0].team_size == 5
    assert proposals[0].role_diversity_score == 1.0
