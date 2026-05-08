from datetime import datetime, timezone
from types import SimpleNamespace

from cogs.accueil.presenters import (
    build_member_stats_embed,
    build_welcome_embed,
    detect_period_from_embed,
)


def test_build_welcome_embed_keeps_mentions_and_assets() -> None:
    embed = build_welcome_embed(
        username="Victor",
        rules_mention="<#1>",
        introductions_mention="<#2>",
        member_avatar_url="https://example.test/member.png",
        bot_avatar_url="https://example.test/bot.png",
    )

    assert embed.title == "🎉 Bienvenue sur le serveur ! 🎉"
    assert "Salut **Victor**" in embed.description
    assert "<#1>" in embed.description
    assert "<#2>" in embed.description
    assert embed.thumbnail.url == "https://example.test/member.png"
    assert embed.footer.icon_url == "https://example.test/bot.png"


def test_build_member_stats_embed_keeps_stats_and_image() -> None:
    stats_data = SimpleNamespace(
        period_label="30 jours",
        current_members=42,
        join_count=10,
        leave_count=3,
        ratio="3.33",
    )

    embed = build_member_stats_embed(
        stats_data=stats_data,
        timestamp=datetime(2026, 5, 8, tzinfo=timezone.utc),
        image_url="attachment://evolution_membres.png",
    )

    assert embed.title == "Statistiques du serveur"
    assert embed.description == "Période : 30 jours"
    assert embed.fields[0].value == "42"
    assert embed.fields[1].value == "10"
    assert embed.fields[2].value == "3"
    assert embed.image.url == "attachment://evolution_membres.png"


def test_detect_period_from_embed_reads_description() -> None:
    message = SimpleNamespace(
        embeds=[SimpleNamespace(description="Période : 7 jours")]
    )

    assert detect_period_from_embed(message) == "7j"
    assert detect_period_from_embed(SimpleNamespace(embeds=[])) == "default"
