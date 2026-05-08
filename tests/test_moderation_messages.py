from datetime import datetime, timezone
from types import SimpleNamespace

from cogs.moderation.presenters import (
    build_ban_dm_embed,
    build_unban_dm_embed,
    format_ban_status_message,
)


def test_format_ban_status_message_includes_expected_fields() -> None:
    ban_info = SimpleNamespace(
        ban_type="temp",
        reason="test",
        ban_end=datetime(2026, 5, 9, tzinfo=timezone.utc),
        banned_at=datetime(2026, 5, 8, tzinfo=timezone.utc),
        moderator_discord_id=123,
    )

    message = format_ban_status_message(ban_info, banned_user_id=456)

    assert "**Statut de <@456>**" in message
    assert "Type : temp" in message
    assert "Raison : test" in message
    assert "Banni(e) par : <@123>" in message


def test_build_ban_dm_embed_keeps_visible_content() -> None:
    embed = build_ban_dm_embed(
        guild_name="Perfect Team",
        reason="raison",
        duration_label="Permanente",
        banned_by_display_name="Admin",
        deban_channel_mention="<#42>",
        timestamp=datetime(2026, 5, 8, tzinfo=timezone.utc),
    )

    assert embed.title == "📛 Vous avez été banni(e) du serveur"
    assert embed.fields[0].value == "**Perfect Team**"
    assert embed.fields[1].value == "raison"
    assert "<#42>" in embed.fields[4].value


def test_build_unban_dm_embed_keeps_visible_content() -> None:
    embed = build_unban_dm_embed(
        guild_name="Perfect Team",
        reason="ok",
        timestamp=datetime(2026, 5, 8, tzinfo=timezone.utc),
    )

    assert embed.title == "✅ Vous avez été débanni(e) du serveur"
    assert embed.fields[0].value == "**Perfect Team**"
    assert embed.fields[1].value == "ok"
