from __future__ import annotations

from types import SimpleNamespace

import pytest

from cogs.role_management.game_role import GameRoleCog
from cogs.role_management.language_role import LanguageRoleCog
from cogs.role_management.services.role_selection_service import (
    GAME_ROLE_KEYS,
    GAME_ROLE_MESSAGE_TYPE,
    LANGUAGE_ROLE_MESSAGE_TYPE,
    RoleSelectionService,
)
from cogs.role_management.views import GameRolesView, LanguageRolesView
from database.services.persistent_messages_service import PersistentMessageInfo


class FakeRoleConfigService:
    def __init__(self) -> None:
        self.roles = {
            "initiator": 10,
            "controller": 11,
            "duelist": 12,
            "sentinel": 13,
            "fill": 14,
            "francais": 20,
        }

    async def get_all(self, guild_id: int):
        return dict(self.roles)

    async def get_one(self, guild_id: int, key: str):
        return self.roles.get(key)


class FakePersistentMessagesService:
    def __init__(self) -> None:
        self.saved = None

    async def get(self, guild_id: int, message_type: str):
        if self.saved is None or self.saved["message_type"] != message_type:
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
        return True


@pytest.mark.asyncio
async def test_role_selection_gets_configured_roles_and_missing_keys() -> None:
    service = RoleSelectionService(FakeRoleConfigService(), FakePersistentMessagesService())

    configured = await service.get_configured_role_ids(1, GAME_ROLE_KEYS)

    assert configured == {
        "initiator": 10,
        "controller": 11,
        "duelist": 12,
        "sentinel": 13,
        "fill": 14,
    }
    assert service.missing_config_keys(configured, (*GAME_ROLE_KEYS, "missing")) == ("missing",)


def test_role_selection_builds_exclusive_valorant_plan() -> None:
    service = RoleSelectionService(FakeRoleConfigService(), FakePersistentMessagesService())

    plan = service.build_exclusive_selection_plan(
        current_role_ids={10, 11, 99},
        configured_role_ids={"initiator": 10, "controller": 11, "duelist": 12},
        selected_key="duelist",
    )

    assert plan.role_to_add_id == 12
    assert plan.role_ids_to_remove == (10, 11)
    assert plan.already_selected is False


def test_role_selection_detects_already_selected_valorant_role() -> None:
    service = RoleSelectionService(FakeRoleConfigService(), FakePersistentMessagesService())

    plan = service.build_exclusive_selection_plan(
        current_role_ids={10, 99},
        configured_role_ids={"initiator": 10, "controller": 11},
        selected_key="initiator",
    )

    assert plan.role_to_add_id is None
    assert plan.role_ids_to_remove == ()
    assert plan.already_selected is True


def test_role_selection_builds_language_toggle_plans() -> None:
    service = RoleSelectionService(FakeRoleConfigService(), FakePersistentMessagesService())

    add_plan = service.build_toggle_plan(current_role_ids={99}, role_id=20)
    remove_plan = service.build_toggle_plan(current_role_ids={20, 99}, role_id=20)

    assert add_plan.role_to_add_id == 20
    assert add_plan.role_ids_to_remove == ()
    assert remove_plan.role_to_add_id is None
    assert remove_plan.role_ids_to_remove == (20,)


@pytest.mark.asyncio
async def test_role_selection_stores_persistent_messages() -> None:
    messages = FakePersistentMessagesService()
    service = RoleSelectionService(FakeRoleConfigService(), messages)

    await service.save_persistent_message(
        guild_id=1,
        guild_name="Perfect Team",
        message_type=GAME_ROLE_MESSAGE_TYPE,
        channel_id=10,
        message_id=20,
    )
    game_message = await service.get_persistent_message(1, GAME_ROLE_MESSAGE_TYPE)
    language_message = await service.get_persistent_message(1, LANGUAGE_ROLE_MESSAGE_TYPE)

    assert game_message == PersistentMessageInfo(channel_id=10, message_id=20)
    assert language_message is None


@pytest.mark.asyncio
async def test_role_cogs_register_persistent_views() -> None:
    bot = SimpleNamespace(views=[], add_view=lambda view: bot.views.append(view))

    GameRoleCog(bot, object())
    LanguageRoleCog(bot, object())

    assert [type(view) for view in bot.views] == [GameRolesView, LanguageRolesView]
