from __future__ import annotations

import importlib

import pytest


ACTIVE_COGS = [
    "cogs.configuration.channels_configuration",
    "cogs.configuration.roles_configuration",
    "cogs.accueil.accueil",
    "cogs.accueil.stalker",
    "cogs.admin.status",
    "cogs.admin.permissions_report",
    "cogs.moderation.clean",
    "cogs.moderation.moderation",
    "cogs.moderation.automod",
    "cogs.moderation.unban_requests",
    "cogs.file_counter.file_counter",
    "cogs.reputation.reputation",
    "cogs.rules.rules",
    "cogs.role_management.game_role",
    "cogs.role_management.language_role",
    "cogs.twitch.twitch",
    "cogs.voice_chat.temp_voice",
    "cogs.ranking.assign_rank",
    "cogs.ranking.rank_notifications",
    "cogs.ranking.mmr_tracker",
]


@pytest.mark.parametrize("module_name", ACTIVE_COGS)
def test_active_cog_imports(module_name: str):
    importlib.import_module(module_name)


def test_bot_entrypoint_imports():
    module = importlib.import_module("bot")

    assert module.COG_PATHS == ACTIVE_COGS
