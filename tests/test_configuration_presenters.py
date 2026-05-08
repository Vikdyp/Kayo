from types import SimpleNamespace

from cogs.configuration.presenters import (
    build_channels_list_embed,
    build_channels_status_embed,
    build_roles_list_embed,
    build_roles_status_embed,
    get_channel_display_name,
)


class FakeGuild:
    def __init__(self) -> None:
        self._channels = {
            10: SimpleNamespace(mention="<#10>"),
        }
        self._roles = {
            20: SimpleNamespace(mention="<@&20>"),
        }

    def get_channel(self, channel_id: int):
        return self._channels.get(channel_id)

    def get_role(self, role_id: int):
        return self._roles.get(role_id)


def test_get_channel_display_name_falls_back() -> None:
    assert get_channel_display_name("rang", {"rang": "Salon rang"}) == "Salon rang"
    assert get_channel_display_name("rank_up", {}) == "Rank up"


def test_build_channels_list_embed_marks_missing_channels() -> None:
    embed = build_channels_list_embed(
        FakeGuild(),
        {"rang": 10, "rules": 11},
        {"rang": "Salon rang", "rules": "Règles"},
    )

    assert embed.title == "Salons configurés"
    assert embed.fields[0].value == "<#10>"
    assert "Salon introuvable" in embed.fields[1].value


def test_build_channels_status_embed_counts_configured_and_missing() -> None:
    embed = build_channels_status_embed(
        FakeGuild(),
        {"rang": 10},
        [("rang", "Salon rang"), ("rules", "Règles")],
        {"rang": "Salon rang", "rules": "Règles"},
    )

    assert embed.title == "Configuration des salons"
    assert embed.fields[0].name == "Configurés (1)"
    assert "Salon rang" in embed.fields[0].value
    assert embed.fields[1].name == "À configurer (1)"
    assert "Règles" in embed.fields[1].value


def test_build_roles_list_embed_marks_missing_roles() -> None:
    embed = build_roles_list_embed(FakeGuild(), {"admin": 20, "ban": 21})

    assert embed.title == "Rôles configurés"
    assert embed.fields[0].value == "<@&20>"
    assert "Rôle introuvable" in embed.fields[1].value


def test_build_roles_status_embed_counts_configured_and_missing() -> None:
    embed = build_roles_status_embed(FakeGuild(), {"admin": 20}, ["admin", "ban"])

    assert embed.title == "Configuration des rôles"
    assert embed.fields[0].name == "Configurés (1)"
    assert "`admin`" in embed.fields[0].value
    assert embed.fields[1].name == "À configurer (1)"
    assert "`ban`" in embed.fields[1].value
