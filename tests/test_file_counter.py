from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from cogs.file_counter.file_counter import FileCounterCog
from cogs.file_counter.presenters import build_file_counter_embed, calculate_completion_percentage
from cogs.file_counter.services import FILE_COUNTER_CHANNEL_KEY, FileCounterService
from cogs.file_counter.views import FileCounterView
from database.services.file_counters_service import FileCounterInfo


@dataclass
class FakeFileCounterDbService:
    counter: FileCounterInfo | None = None

    async def get_counter(self, guild_id: int, channel_id: int):
        return self.counter

    async def list_counters(self):
        return [self.counter] if self.counter else []

    async def reset_counter(self, *, guild_id: int, guild_name: str | None, channel_id: int, message_id: int):
        self.counter = FileCounterInfo(
            guild_id=guild_id,
            channel_id=channel_id,
            message_id=message_id,
            added_count=0,
            completed_count=0,
        )
        return self.counter

    async def increment_counter(
        self,
        *,
        guild_id: int,
        channel_id: int,
        added_delta: int = 0,
        completed_delta: int = 0,
    ):
        if self.counter is None:
            return None
        self.counter = FileCounterInfo(
            guild_id=guild_id,
            channel_id=channel_id,
            message_id=self.counter.message_id,
            added_count=self.counter.added_count + added_delta,
            completed_count=self.counter.completed_count + completed_delta,
        )
        return self.counter


class FakeChannelConfigService:
    async def get_one(self, guild_id: int, key: str):
        if key == FILE_COUNTER_CHANNEL_KEY:
            return 42
        return None


def make_service(db: FakeFileCounterDbService | None = None) -> FileCounterService:
    return FileCounterService(db or FakeFileCounterDbService(), FakeChannelConfigService())


def test_file_counter_percentage_is_capped() -> None:
    assert calculate_completion_percentage(added_count=0, completed_count=1) == 0.0
    assert calculate_completion_percentage(added_count=4, completed_count=2) == 50.0
    assert calculate_completion_percentage(added_count=1, completed_count=3) == 100


def test_file_counter_embed_uses_counts() -> None:
    embed = build_file_counter_embed(added_count=4, completed_count=2)

    assert embed.title == "Suivi des fichiers"
    assert "Fichiers ajoutes**: 4" in embed.description
    assert "Fichiers termines**: 2" in embed.description
    assert "Completion**: 50.0%" in embed.description


@pytest.mark.asyncio
async def test_file_counter_service_uses_configured_channel_and_increments() -> None:
    db = FakeFileCounterDbService()
    service = make_service(db)

    assert await service.get_configured_channel_id(1) == 42

    await service.reset_counter(guild_id=1, guild_name="Guild", channel_id=42, message_id=99)
    added = await service.increment_added(guild_id=1, channel_id=42)
    completed = await service.increment_completed(guild_id=1, channel_id=42)

    assert added.added_count == 1
    assert added.completed_count == 0
    assert completed.added_count == 1
    assert completed.completed_count == 1


@pytest.mark.asyncio
async def test_file_counter_cog_registers_persistent_view() -> None:
    bot = SimpleNamespace(views=[], add_view=lambda view: bot.views.append(view))

    FileCounterCog(bot, object())

    assert [type(view) for view in bot.views] == [FileCounterView]
    assert [item.custom_id for item in bot.views[0].children] == [
        "file_counter:ajouter",
        "file_counter:terminer",
    ]
