from datetime import datetime, timezone

from cogs.moderation.presenters import (
    build_automod_status_embed,
    build_scam_ban_dm_embed,
    build_scam_log_embed,
    build_spam_alert_embed,
    build_spam_ban_dm_embed,
    format_custom_items_message,
    mark_spam_alert_banned,
    mark_spam_alert_ignored,
)


def test_format_custom_items_message_handles_empty_and_values() -> None:
    assert format_custom_items_message(
        label="Patterns personnalisés",
        items=[],
        empty_message="Aucun pattern personnalisé configuré.",
    ) == "Aucun pattern personnalisé configuré."

    message = format_custom_items_message(
        label="Domaines personnalisés",
        items=["example.test", "bad.test"],
        empty_message="empty",
    )
    assert "📋 **Domaines personnalisés (2):**" in message
    assert "• `example.test`" in message


def test_build_automod_status_embed_summarizes_config() -> None:
    embed = build_automod_status_embed(
        config={
            "scam_detection_enabled": False,
            "spam_detection_enabled": True,
            "spam_channel_threshold": 4,
            "spam_time_window": 90,
            "whitelisted_roles": [1, 2, 3, 4, 5, 6],
            "whitelisted_channels": [10],
            "custom_scam_patterns": ["x"],
            "custom_scam_domains": ["bad.test", "evil.test"],
        },
        timestamp=datetime(2026, 5, 8, tzinfo=timezone.utc),
    )

    assert embed.title == "⚙️ Configuration AutoMod"
    assert "**Scam:** ❌ Désactivé" in embed.fields[0].value
    assert "Seuil: **4** salons" in embed.fields[1].value
    assert "... +1 autres" in embed.fields[2].value
    assert "**Domaines:** 2" in embed.fields[4].value


def test_build_scam_ban_dm_embed_keeps_reason() -> None:
    embed = build_scam_ban_dm_embed(
        guild_name="Perfect Team",
        timestamp=datetime(2026, 5, 8, tzinfo=timezone.utc),
    )

    assert embed.title == "📛 Vous avez été banni(e) automatiquement"
    assert embed.fields[0].value == "Perfect Team"
    assert embed.fields[1].value == "Message de scam détecté"


def test_build_scam_log_embed_truncates_content() -> None:
    embed = build_scam_log_embed(
        user_mention="<@1>",
        user_id=1,
        user_avatar_url="https://example.test/avatar.png",
        channel_mention="<#2>",
        content="x" * 1001,
        timestamp=datetime(2026, 5, 8, tzinfo=timezone.utc),
    )

    assert embed.title == "🚨 Scam détecté - Ban automatique"
    assert embed.fields[0].value == "<@1> (1)"
    assert len(embed.fields[3].value) == 1000
    assert embed.fields[3].value.endswith("...")


def test_build_spam_alert_embed_keeps_channel_links() -> None:
    embed = build_spam_alert_embed(
        user_mention="<@1>",
        user_id=1,
        user_avatar_url="https://example.test/avatar.png",
        content="same message",
        channel_mentions=["• <#2> ([message](url))"],
        timestamp=datetime(2026, 5, 8, tzinfo=timezone.utc),
    )

    assert embed.title == "⚠️ Spam multi-salons détecté"
    assert embed.fields[0].value == "<@1> (1)"
    assert embed.fields[1].value == "same message"
    assert "• <#2>" in embed.fields[2].value


def test_build_spam_ban_dm_embed_keeps_reason() -> None:
    embed = build_spam_ban_dm_embed(
        guild_name="Perfect Team",
        timestamp=datetime(2026, 5, 8, tzinfo=timezone.utc),
    )

    assert embed.title == "📛 Vous avez été banni(e)"
    assert embed.fields[0].value == "Perfect Team"
    assert embed.fields[1].value == "Spam multi-salons détecté"


def test_mark_spam_alert_banned_and_ignored_append_result_fields() -> None:
    banned_embed = build_spam_alert_embed(
        user_mention="<@1>",
        user_id=1,
        user_avatar_url="https://example.test/avatar.png",
        content="same message",
        channel_mentions=[],
        timestamp=datetime(2026, 5, 8, tzinfo=timezone.utc),
    )
    mark_spam_alert_banned(banned_embed, moderator_mention="<@2>", deleted_count=3)

    assert banned_embed.fields[-1].name == "✅ Action effectuée"
    assert "Banni par <@2>" in banned_embed.fields[-1].value
    assert "3 message(s)" in banned_embed.fields[-1].value

    ignored_embed = build_spam_alert_embed(
        user_mention="<@1>",
        user_id=1,
        user_avatar_url="https://example.test/avatar.png",
        content="same message",
        channel_mentions=[],
        timestamp=datetime(2026, 5, 8, tzinfo=timezone.utc),
    )
    mark_spam_alert_ignored(ignored_embed, moderator_mention="<@2>")

    assert ignored_embed.fields[-1].name == "❌ Ignoré"
    assert "Ignoré par <@2>" in ignored_embed.fields[-1].value
