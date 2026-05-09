from __future__ import annotations

from types import SimpleNamespace

import pytest

from cogs.rules.rules import RulesCog
from cogs.rules.services.rules_service import RULES_MESSAGE_TYPE, RulesService
from cogs.rules.views import AcceptRulesView
from database.services.guild_members_service import RulesAcceptanceResult
from database.services.persistent_messages_service import PersistentMessageInfo


class FakeChannelConfigService:
    async def get_one(self, guild_id: int, key: str):
        return 123 if key == "rules" else None


class FakeGuildMembersService:
    def __init__(self, result: RulesAcceptanceResult) -> None:
        self.result = result
        self.accept_args = None

    async def has_accepted_rules(self, *, guild_id: int, discord_user_id: int) -> bool:
        return self.result.already_accepted

    async def accept_rules(self, *, guild_id: int, guild_name: str | None, discord_user_id: int):
        self.accept_args = (guild_id, guild_name, discord_user_id)
        return self.result


class FakePersistentMessagesService:
    def __init__(self) -> None:
        self.saved = None
        self.deleted = None

    async def get(self, guild_id: int, message_type: str):
        if self.saved is None:
            return None
        return PersistentMessageInfo(channel_id=self.saved["channel_id"], message_id=self.saved["message_id"])

    async def save(self, *, guild_id: int, guild_name: str | None, message_type: str, channel_id: int, message_id: int):
        self.saved = {
            "guild_id": guild_id,
            "guild_name": guild_name,
            "message_type": message_type,
            "channel_id": channel_id,
            "message_id": message_id,
        }

    async def delete(self, guild_id: int, message_type: str) -> bool:
        self.deleted = (guild_id, message_type)
        return True


@pytest.mark.asyncio
async def test_rules_service_accepts_new_user() -> None:
    members = FakeGuildMembersService(RulesAcceptanceResult(accepted=True, already_accepted=False))
    service = RulesService(FakeChannelConfigService(), members, FakePersistentMessagesService())

    result = await service.accept_rules(guild_id=1, guild_name="Perfect Team", discord_user_id=42)

    assert result.accepted is True
    assert result.already_accepted is False
    assert members.accept_args == (1, "Perfect Team", 42)


@pytest.mark.asyncio
async def test_rules_service_reports_already_accepted_user() -> None:
    members = FakeGuildMembersService(RulesAcceptanceResult(accepted=False, already_accepted=True))
    service = RulesService(FakeChannelConfigService(), members, FakePersistentMessagesService())

    result = await service.accept_rules(guild_id=1, guild_name="Perfect Team", discord_user_id=42)

    assert result.accepted is False
    assert result.already_accepted is True


@pytest.mark.asyncio
async def test_rules_service_stores_persistent_message() -> None:
    messages = FakePersistentMessagesService()
    service = RulesService(
        FakeChannelConfigService(),
        FakeGuildMembersService(RulesAcceptanceResult(accepted=True, already_accepted=False)),
        messages,
    )

    await service.save_rules_message(guild_id=1, guild_name="Perfect Team", channel_id=10, message_id=20)
    stored = await service.get_rules_message(1)

    assert messages.saved["message_type"] == RULES_MESSAGE_TYPE
    assert stored == PersistentMessageInfo(channel_id=10, message_id=20)


@pytest.mark.asyncio
async def test_rules_cog_registers_persistent_view() -> None:
    bot = SimpleNamespace(views=[], add_view=lambda view: bot.views.append(view))

    RulesCog(bot, object())

    assert len(bot.views) == 1
    assert isinstance(bot.views[0], AcceptRulesView)
