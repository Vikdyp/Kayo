# cogs/moderation/presenters/moderation_messages.py
"""Embeds and display messages for moderation workflows."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

import discord


class BanDisplayInfo(Protocol):
    ban_type: str | None
    reason: str | None
    ban_end: datetime | None
    banned_at: datetime | None
    moderator_discord_id: int | None


def format_ban_status_message(ban_info: BanDisplayInfo, banned_user_id: int) -> str:
    ban_type = ban_info.ban_type or "Inconnu"
    reason = ban_info.reason or "Aucune raison fournie"
    ban_end = ban_info.ban_end or "Permanent"
    banned_at = ban_info.banned_at or "Inconnu"
    banned_by = (
        f"<@{ban_info.moderator_discord_id}>"
        if ban_info.moderator_discord_id
        else "Inconnu"
    )

    return (
        f"**Statut de <@{banned_user_id}>** :\n"
        f"Type : {ban_type}\n"
        f"Raison : {reason}\n"
        f"Banni(e) le : {banned_at}\n"
        f"Fin de ban : {ban_end}\n"
        f"Banni(e) par : {banned_by}"
    )


def build_ban_dm_embed(
    *,
    guild_name: str,
    reason: str,
    duration_label: str,
    banned_by_display_name: str,
    deban_channel_mention: str,
    timestamp: datetime,
) -> discord.Embed:
    embed = discord.Embed(
        title="📛 Vous avez été banni(e) du serveur",
        color=discord.Color.red(),
        timestamp=timestamp,
    )
    embed.add_field(name="Serveur", value=f"**{guild_name}**", inline=False)
    embed.add_field(name="Raison", value=reason, inline=False)
    embed.add_field(name="Durée", value=duration_label, inline=False)
    embed.add_field(name="Banni(e) par", value=banned_by_display_name, inline=False)
    embed.add_field(
        name="Demande de Débannissement",
        value=(
            "Si vous souhaitez être débanni(e), veuillez soumettre une demande "
            f"dans {deban_channel_mention}."
        ),
        inline=False,
    )
    embed.set_footer(text="Si vous avez des questions, veuillez contacter l'administration.")
    return embed


def build_unban_dm_embed(
    *,
    guild_name: str,
    reason: str,
    timestamp: datetime,
) -> discord.Embed:
    embed = discord.Embed(
        title="✅ Vous avez été débanni(e) du serveur",
        color=discord.Color.green(),
        timestamp=timestamp,
    )
    embed.add_field(name="Serveur", value=f"**{guild_name}**", inline=False)
    embed.add_field(name="Raison", value=reason, inline=False)
    embed.add_field(name="Débanni(e) par", value="Administration", inline=False)
    embed.add_field(
        name="C'est fini",
        value=(
            "Bonne nouvelle, vous êtes libre comme l’air. On est content de vous revoir "
            "parmi nous, mais faites gaffe cette fois, hein ? 😉 Profitez bien et bon retour !"
        ),
        inline=False,
    )
    embed.set_footer(text="Si vous avez des questions, veuillez contacter l'administration.")
    return embed
