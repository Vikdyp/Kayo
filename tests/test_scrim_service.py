from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from cogs.scrims.presenters import build_scrim_embed, format_team, join_status_message
from cogs.scrims.services import SCRIM_CREATION_MESSAGE_TYPE, ScrimService
from database.services.persistent_messages_service import PersistentMessageInfo
from database.services.scrims_service import ScrimInfo, ScrimJoinResult, ScrimLeaveResult

PARIS_TZ = ZoneInfo("Europe/Paris")


class FakeScrimsDb:
    def __init__(self) -> None:
        self.scrim = ScrimInfo(
            id=1,
            guild_id=10,
            creator_discord_id=100,
            scheduled_at=datetime(2026, 5, 10, 20, 0, tzinfo=PARIS_TZ),
            map_name="Ascent",
            rank_name="Or",
            notes="BO1",
            team1_discord_ids=(100,),
            team2_discord_ids=(),
            channel_id=None,
            message_id=None,
            status="active",
        )

    async def create_scrim(self, **kwargs):
        return self.scrim

    async def save_message(self, *, scrim_id: int, channel_id: int, message_id: int):
        self.scrim = replace(self.scrim, channel_id=channel_id, message_id=message_id)
        return self.scrim

    async def get_scrim(self, scrim_id: int):
        return self.scrim if scrim_id == self.scrim.id else None

    async def list_active_scrims(self, guild_id: int | None = None):
        return (self.scrim,) if guild_id in {None, self.scrim.guild_id} else ()

    async def list_due_scrims(self, *, now: datetime):
        return (self.scrim,) if self.scrim.scheduled_at <= now else ()

    async def join_team(self, **kwargs):
        self.scrim = replace(self.scrim, team2_discord_ids=(200,))
        return ScrimJoinResult(status="joined", scrim=self.scrim)

    async def leave_scrim(self, **kwargs):
        self.scrim = replace(self.scrim, team1_discord_ids=())
        return ScrimLeaveResult(status="left", scrim=self.scrim)

    async def mark_completed(self, scrim_id: int) -> bool:
        return scrim_id == self.scrim.id


class FakePersistentMessages:
    def __init__(self) -> None:
        self.saved: dict[str, int | str | None] = {}

    async def save(self, *, guild_id: int, guild_name: str | None, message_type: str, channel_id: int, message_id: int):
        self.saved = {
            "guild_id": guild_id,
            "guild_name": guild_name,
            "message_type": message_type,
            "channel_id": channel_id,
            "message_id": message_id,
        }

    async def get(self, guild_id: int, message_type: str):
        if self.saved.get("guild_id") != guild_id or self.saved.get("message_type") != message_type:
            return None
        return PersistentMessageInfo(channel_id=int(self.saved["channel_id"]), message_id=int(self.saved["message_id"]))


class FakeRules:
    async def has_accepted_rules(self, *, guild_id: int, discord_user_id: int) -> bool:
        return discord_user_id == 100


def make_service(db: FakeScrimsDb | None = None, messages: FakePersistentMessages | None = None) -> ScrimService:
    return ScrimService(db or FakeScrimsDb(), messages or FakePersistentMessages(), FakeRules())


def test_scrim_service_parses_creation_data() -> None:
    data = ScrimService.parse_creation_data(
        date_raw="10/05/2026",
        time_raw="20:30",
        map_name="  Ascent  ",
        rank_name=" Or ",
        notes="  BO1  ",
    )

    assert data.scheduled_at == datetime(2026, 5, 10, 20, 30, tzinfo=PARIS_TZ)
    assert data.map_name == "Ascent"
    assert data.rank_name == "Or"
    assert data.notes == "BO1"


def test_scrim_service_rejects_empty_map_or_rank() -> None:
    with pytest.raises(ValueError):
        ScrimService.parse_creation_data(
            date_raw="10/05/2026",
            time_raw="20:30",
            map_name="",
            rank_name="Or",
            notes="",
        )


@pytest.mark.asyncio
async def test_scrim_service_delegates_create_join_leave_and_persistent_message() -> None:
    messages = FakePersistentMessages()
    service = make_service(messages=messages)
    data = ScrimService.parse_creation_data(
        date_raw="10/05/2026",
        time_raw="20:30",
        map_name="Ascent",
        rank_name="Or",
        notes="",
    )

    created = await service.create_scrim(
        guild_id=10,
        guild_name="Guild",
        creator_discord_id=100,
        data=data,
    )
    joined = await service.join_team(guild_id=10, guild_name="Guild", scrim_id=1, discord_user_id=200, team="team2")
    left = await service.leave_scrim(guild_id=10, scrim_id=1, discord_user_id=100)
    await service.save_creation_message(guild_id=10, guild_name="Guild", channel_id=20, message_id=30)

    assert created.id == 1
    assert joined.status == "joined"
    assert left.status == "left"
    assert await service.get_creation_message(10) == PersistentMessageInfo(channel_id=20, message_id=30)
    assert messages.saved["message_type"] == SCRIM_CREATION_MESSAGE_TYPE


@pytest.mark.asyncio
async def test_scrim_service_checks_rules_acceptance() -> None:
    service = make_service()

    assert await service.has_accepted_rules(guild_id=10, discord_user_id=100) is True
    assert await service.has_accepted_rules(guild_id=10, discord_user_id=200) is False


def test_scrim_presenter_builds_embed() -> None:
    scrim = FakeScrimsDb().scrim
    embed = build_scrim_embed(scrim)

    assert embed.title == "Scrim de <@100>"
    assert embed.fields[0].name == "Map"
    assert "Ascent" in embed.fields[0].value
    assert format_team(()) == "En attente..."
    assert join_status_message("full", team_label="l'equipe 1") == "l'equipe 1 est deja complete."
