from __future__ import annotations

import pytest

from cogs.twitch.presenters import abbreviate_number, format_streamer_list
from cogs.twitch.services import TwitchNotificationService, normalize_streamer_login


class FakeTwitchDb:
    def __init__(self) -> None:
        self.streamers: dict[int, set[str]] = {}

    async def add_streamer(self, *, guild_id: int, guild_name: str | None, streamer_login: str) -> bool:
        values = self.streamers.setdefault(guild_id, set())
        if streamer_login in values:
            return False
        values.add(streamer_login)
        return True

    async def remove_streamer(self, *, guild_id: int, streamer_login: str) -> bool:
        values = self.streamers.setdefault(guild_id, set())
        if streamer_login not in values:
            return False
        values.remove(streamer_login)
        return True

    async def list_streamers(self, guild_id: int) -> list[str]:
        return sorted(self.streamers.get(guild_id, set()))


class FakeChannels:
    async def get_one(self, guild_id: int, key: str) -> int | None:
        return 123 if key == "twitch" else None


def make_service(db: FakeTwitchDb | None = None) -> TwitchNotificationService:
    return TwitchNotificationService(db or FakeTwitchDb(), FakeChannels())


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Curs4d", "curs4d"),
        ("@Curs4d", "curs4d"),
        (" stream_user ", "stream_user"),
    ],
)
def test_normalize_streamer_login_accepts_twitch_names(raw: str, expected: str) -> None:
    assert normalize_streamer_login(raw) == expected


@pytest.mark.parametrize("raw", ["", "ab", "with-dash", "with space", "too_long_" * 4])
def test_normalize_streamer_login_rejects_invalid_names(raw: str) -> None:
    assert normalize_streamer_login(raw) is None


@pytest.mark.asyncio
async def test_twitch_service_add_remove_and_list() -> None:
    db = FakeTwitchDb()
    service = make_service(db)

    created = await service.add_streamer(guild_id=1, guild_name="Guild", streamer="Curs4d")
    duplicate = await service.add_streamer(guild_id=1, guild_name="Guild", streamer="curs4d")
    listed = await service.list_streamers(1)
    removed = await service.remove_streamer(guild_id=1, streamer="curs4d")
    missing = await service.remove_streamer(guild_id=1, streamer="curs4d")

    assert created.status == "created"
    assert duplicate.status == "already_exists"
    assert listed == ["curs4d"]
    assert removed.status == "removed"
    assert missing.status == "not_found"


@pytest.mark.asyncio
async def test_twitch_service_reads_notify_channel() -> None:
    assert await make_service().get_notify_channel_id(1) == 123


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (9999, "9999"),
        (10000, "10k"),
        (15999, "15k"),
        (1_000_000, "1m"),
        (1_500_000, "1.5m"),
    ],
)
def test_abbreviate_number(value: int, expected: str) -> None:
    assert abbreviate_number(value) == expected


def test_format_streamer_list() -> None:
    assert format_streamer_list([]) == "Aucun streamer configure."
    assert format_streamer_list(["a", "b"]) == "Streamers: `a`, `b`"
