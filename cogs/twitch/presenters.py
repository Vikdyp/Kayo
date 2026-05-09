from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import discord


@dataclass(frozen=True, slots=True)
class TwitchLiveNotification:
    streamer_login: str
    title: str
    game_name: str
    viewer_count: int
    follower_count: int
    stream_url: str
    thumbnail_url: str | None = None
    profile_image_url: str | None = None
    box_art_url: str | None = None
    timestamp: datetime | None = None


def abbreviate_number(value: int) -> str:
    if value >= 1_000_000:
        millions = value / 1_000_000
        return f"{int(millions)}m" if millions.is_integer() else f"{millions:.1f}m"
    if value >= 10_000:
        return f"{value // 1_000}k"
    return str(value)


def build_twitch_live_embed(notification: TwitchLiveNotification) -> discord.Embed:
    embed = discord.Embed(
        title=f"{notification.streamer_login} est en live",
        url=notification.stream_url,
        description=f"**{notification.title or 'Live Twitch'}**",
        color=discord.Color.purple(),
    )
    if notification.profile_image_url:
        embed.set_author(
            name=notification.streamer_login,
            icon_url=notification.profile_image_url,
            url=notification.stream_url,
        )
    if notification.thumbnail_url:
        embed.set_image(url=notification.thumbnail_url)
    if notification.box_art_url or notification.profile_image_url:
        embed.set_thumbnail(url=notification.box_art_url or notification.profile_image_url)
    embed.add_field(name="Categorie", value=notification.game_name or "Inconnu", inline=True)
    embed.add_field(name="Followers", value=abbreviate_number(notification.follower_count), inline=True)
    embed.add_field(name="Viewers", value=abbreviate_number(notification.viewer_count), inline=True)
    embed.timestamp = notification.timestamp
    return embed


def format_streamer_list(streamers: list[str]) -> str:
    if not streamers:
        return "Aucun streamer configure."
    return "Streamers: " + ", ".join(f"`{streamer}`" for streamer in streamers)
