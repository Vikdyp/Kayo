# cogs/ranking/presenters/mmr_stats_messages.py
"""Embeds for MMR tracking stats."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

import discord


class MmrStatsDisplay(Protocol):
    total_games: int
    total_change: int
    avg_win: int
    avg_loss: int
    last_diff: int


def build_mmr_stats_embed(
    *,
    title: str,
    stats: MmrStatsDisplay,
    timestamp: datetime,
) -> discord.Embed:
    embed = discord.Embed(
        title=f"📊 Stats MMR – {title}",
        description=(
            f"Total games: **{stats.total_games}**\n"
            f"Total {title.lower()}: **{stats.total_change:+d}**\n"
            f"Moyenne win: **{stats.avg_win:+d}**\n"
            f"Moyenne loss: **{stats.avg_loss:+d}**\n"
            f"Dernière game: **{stats.last_diff:+d}**"
        ),
        timestamp=timestamp,
    )
    embed.set_image(url="attachment://mmr_history.png")
    return embed
