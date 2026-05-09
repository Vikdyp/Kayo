from __future__ import annotations

from types import SimpleNamespace

import pytest

from cogs.voice_chat.services import TempVoiceConfig, TempVoiceService
from cogs.voice_chat.services.temp_voice_service import TEMP_VOCAL_CATEGORY_KEY, TEMP_VOCAL_LOBBY_KEY


class FakeChannelConfigService:
    def __init__(self) -> None:
        self.values = {
            TEMP_VOCAL_CATEGORY_KEY: 10,
            TEMP_VOCAL_LOBBY_KEY: 20,
        }

    async def get_one(self, guild_id: int, key: str):
        return self.values.get(key)


def make_channel(*, channel_id: int = 1, category_id: int | None = 10, members: list[object] | None = None):
    category = None if category_id is None else SimpleNamespace(id=category_id)
    return SimpleNamespace(
        id=channel_id,
        name="Salon de Test",
        category=category,
        members=[] if members is None else members,
    )


@pytest.mark.asyncio
async def test_temp_voice_service_reads_config_from_channel_config() -> None:
    service = TempVoiceService(FakeChannelConfigService())

    config = await service.get_config(123)

    assert config == TempVoiceConfig(category_id=10, lobby_channel_id=20)
    assert config.is_complete is True


def test_temp_voice_service_detects_lobby_join() -> None:
    service = TempVoiceService(FakeChannelConfigService())
    config = TempVoiceConfig(category_id=10, lobby_channel_id=20)

    assert service.is_lobby_join(after_channel_id=20, config=config) is True
    assert service.is_lobby_join(after_channel_id=21, config=config) is False
    assert service.is_lobby_join(after_channel_id=None, config=config) is False


def test_temp_voice_service_detects_temp_channel_and_idle_state() -> None:
    service = TempVoiceService(FakeChannelConfigService())
    config = TempVoiceConfig(category_id=10, lobby_channel_id=20)
    empty_temp_channel = make_channel(category_id=10, members=[])
    occupied_temp_channel = make_channel(category_id=10, members=[object()])
    lobby_channel = make_channel(channel_id=20, category_id=10, members=[])
    other_channel = make_channel(category_id=99, members=[])

    assert service.is_temp_channel(empty_temp_channel, config=config) is True
    assert service.is_temp_channel(lobby_channel, config=config) is False
    assert service.is_temp_channel(other_channel, config=config) is False
    assert service.should_schedule_deletion(empty_temp_channel, config=config) is True
    assert service.should_schedule_deletion(lobby_channel, config=config) is False
    assert service.should_schedule_deletion(occupied_temp_channel, config=config) is False
    assert service.should_cancel_deletion(occupied_temp_channel, config=config) is True
    assert service.should_cancel_deletion(empty_temp_channel, config=config) is False


def test_temp_voice_service_requires_complete_config_for_cleanup() -> None:
    service = TempVoiceService(FakeChannelConfigService())
    channel = make_channel(category_id=10, members=[])

    config_without_lobby = TempVoiceConfig(category_id=10, lobby_channel_id=None)
    config_without_category = TempVoiceConfig(category_id=None, lobby_channel_id=20)

    assert service.is_temp_channel(channel, config=config_without_lobby) is False
    assert service.should_schedule_deletion(channel, config=config_without_lobby) is False
    assert service.is_temp_channel(channel, config=config_without_category) is False


def test_temp_voice_service_builds_stable_channel_name() -> None:
    service = TempVoiceService(FakeChannelConfigService())

    assert service.build_temp_channel_name("Victor") == "Salon de Victor"
