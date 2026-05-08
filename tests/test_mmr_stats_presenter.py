from datetime import datetime, timezone
from types import SimpleNamespace

from cogs.ranking.presenters import build_mmr_stats_embed


def test_build_mmr_stats_embed_keeps_summary_and_image() -> None:
    stats = SimpleNamespace(
        total_games=3,
        total_change=40,
        avg_win=25,
        avg_loss=-10,
        last_diff=30,
    )

    embed = build_mmr_stats_embed(
        title="Aujourd'hui",
        stats=stats,
        timestamp=datetime(2026, 5, 8, tzinfo=timezone.utc),
    )

    assert embed.title == "📊 Stats MMR – Aujourd'hui"
    assert "Total games: **3**" in embed.description
    assert "Total aujourd'hui: **+40**" in embed.description
    assert "Dernière game: **+30**" in embed.description
    assert embed.image.url == "attachment://mmr_history.png"
