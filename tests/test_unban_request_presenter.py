from datetime import datetime, timezone
from types import SimpleNamespace

from cogs.moderation.presenters import (
    build_deban_panel_embed,
    build_deban_request_channel_name,
    build_deban_request_embed,
)


def test_build_deban_panel_embed_keeps_main_copy() -> None:
    embed = build_deban_panel_embed(
        timestamp=datetime(2026, 5, 8, tzinfo=timezone.utc)
    )

    assert embed.title == "🎫 Demande de Déban"
    assert "soumettre une demande de débannissement" in embed.description
    assert embed.footer.text == "Déban Manager"


def test_build_deban_request_channel_name_matches_existing_format() -> None:
    assert build_deban_request_channel_name("User Name") == "deban-user-name"
    assert build_deban_request_channel_name("VeryLongUsernameOverLimit") == "deban-verylongusernameover"


def test_build_deban_request_embed_keeps_ban_details() -> None:
    ban_info = SimpleNamespace(
        ban_type="temp",
        reason=None,
        banned_at=datetime(2026, 5, 8, tzinfo=timezone.utc),
        ban_end=None,
    )

    embed = build_deban_request_embed(
        user_mention="<@42>",
        user_id=42,
        reason="Je demande un déban",
        ban_info=ban_info,
        banned_by_mention="<@1>",
        requester_label="User#0001",
        requester_avatar_url=None,
        timestamp=datetime(2026, 5, 8, tzinfo=timezone.utc),
    )

    assert embed.title == "📄 Nouvelle Demande de Déban"
    assert embed.fields[0].value == "<@42> (`42`)"
    assert embed.fields[1].value == "Je demande un déban"
    assert "Aucune raison fournie" in embed.fields[2].value
    assert "Permanent" in embed.fields[2].value
    assert embed.footer.text == "Demande par User#0001"
