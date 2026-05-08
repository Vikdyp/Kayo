# cogs/moderation/presenters/unban_request_messages.py
"""Embeds and display helpers for unban request workflows."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Protocol

import discord


class BanRequestInfo(Protocol):
    ban_type: str | None
    reason: str | None
    banned_at: datetime | None
    ban_end: datetime | None


def build_deban_request_channel_name(username: str) -> str:
    escaped_username = re.sub(r"([\\*_~|`])", r"\\\1", username)
    sanitized_username = escaped_username.replace(" ", "-").lower()[:20]
    return f"deban-{sanitized_username}"


def build_deban_panel_embed(*, timestamp: datetime) -> discord.Embed:
    embed = discord.Embed(
        title="🎫 Demande de Déban",
        description=(
            "Cliquez sur le bouton ci-dessous pour soumettre une demande de débannissement.\n"
            "Vous serez informé lors du traitement de votre demande."
        ),
        color=discord.Color.blue(),
        timestamp=timestamp,
    )
    embed.set_footer(text="Déban Manager")
    return embed


def build_deban_request_embed(
    *,
    user_mention: str,
    user_id: int,
    reason: str,
    ban_info: BanRequestInfo,
    banned_by_mention: str,
    requester_label: str,
    requester_avatar_url: str | None,
    timestamp: datetime,
) -> discord.Embed:
    embed = discord.Embed(
        title="📄 Nouvelle Demande de Déban",
        color=discord.Color.green(),
        timestamp=timestamp,
    )
    embed.add_field(name="Utilisateur", value=f"{user_mention} (`{user_id}`)", inline=False)
    embed.add_field(name="Raison de la Demande", value=reason, inline=False)
    embed.add_field(
        name="Détails du Bannissement",
        value=(
            f"**Type :** {ban_info.ban_type}\n"
            f"**Raison :** {ban_info.reason or 'Aucune raison fournie'}\n"
            f"**Banni(e) le :** {ban_info.banned_at}\n"
            f"**Fin du ban :** {ban_info.ban_end or 'Permanent'}\n"
            f"**Banni(e) par :** {banned_by_mention}"
        ),
        inline=False,
    )
    embed.set_footer(text=f"Demande par {requester_label}", icon_url=requester_avatar_url)
    return embed
