from datetime import datetime, timezone

from cogs.ranking.presenters import (
    build_duplicate_pseudo_tag_embed,
    build_valorant_account_panel_embed,
    format_valorant_update_error_message,
)


def test_build_valorant_account_panel_embed_keeps_instructions() -> None:
    embed = build_valorant_account_panel_embed()

    assert embed.title == "Gestion de vos informations Valorant"
    assert "renseigner" in embed.description
    assert "Pseudo" in embed.description
    assert embed.footer.text == "Tenez a jour vos informations pour obtenir le role correspondant a votre rang."


def test_build_duplicate_pseudo_tag_embed_keeps_users_and_account() -> None:
    embed = build_duplicate_pseudo_tag_embed(
        existing_user_mention="<@1>",
        existing_user_id=1,
        current_user_mention="<@2>",
        current_user_id=2,
        pseudo="globeX",
        tag="meow",
        timestamp=datetime(2026, 5, 8, tzinfo=timezone.utc),
    )

    assert embed.title == "Doublon de Pseudo Valorant Detecte"
    assert "**globeX#meow**" in embed.description
    assert "<@1> (ID: 1)" in embed.description
    assert "<@2> (ID: 2)" in embed.description
    assert embed.footer.text == "Gestion des Doublons de Pseudo Valorant"


def test_format_valorant_update_error_message_uses_fallback_error() -> None:
    message = format_valorant_update_error_message(
        pseudo="globeX",
        tag="meow",
        error_message=None,
        rank_channel_mention="<#42>",
    )

    assert "**globeX#meow**" in message
    assert "Erreur: Inconnue" in message
    assert "<#42>" in message
