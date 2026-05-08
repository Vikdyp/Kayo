# cogs/accueil/presenters/member_stats_messages.py
"""Member statistics embeds."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

import discord


class StatsEmbedDisplay(Protocol):
    current_members: int
    join_count: int
    leave_count: int
    ratio: str
    period_label: str


def detect_period_from_embed(message: discord.Message) -> str:
    if message.embeds and message.embeds[0].description:
        description = message.embeds[0].description
        if "7 jours" in description:
            return "7j"
        if "1 mois" in description or "30 jours" in description:
            return "1m"
        if "1 an" in description:
            return "1a"
        if "Total" in description:
            return "total"
    return "default"


def build_member_stats_embed(
    *,
    stats_data: StatsEmbedDisplay,
    timestamp: datetime,
    image_url: str | None = None,
) -> discord.Embed:
    embed = discord.Embed(
        title="Statistiques du serveur",
        description=f"Période : {stats_data.period_label}",
        color=discord.Color.green(),
    )
    embed.add_field(name="Membres actuels", value=str(stats_data.current_members), inline=False)
    embed.add_field(name="Adhésions", value=str(stats_data.join_count), inline=True)
    embed.add_field(name="Départs", value=str(stats_data.leave_count), inline=True)
    embed.add_field(name="Taux Join/Leave", value=stats_data.ratio, inline=False)
    embed.set_footer(text="Dernière mise à jour")
    embed.timestamp = timestamp

    if image_url:
        embed.set_image(url=image_url)

    return embed
