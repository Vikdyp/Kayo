# cogs/moderation/presenters/automod_messages.py
"""Embeds and display messages for automod workflows."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence

import discord


def format_custom_items_message(
    *,
    label: str,
    items: Sequence[str],
    empty_message: str,
) -> str:
    if not items:
        return empty_message

    items_text = "\n".join([f"• `{item}`" for item in items])
    return f"📋 **{label} ({len(items)}):**\n{items_text}"


def build_automod_status_embed(
    *,
    config: dict[str, Any],
    timestamp: datetime,
) -> discord.Embed:
    embed = discord.Embed(
        title="⚙️ Configuration AutoMod",
        color=discord.Color.blue(),
        timestamp=timestamp,
    )

    scam_status = "✅ Activé" if config.get("scam_detection_enabled", True) else "❌ Désactivé"
    spam_status = "✅ Activé" if config.get("spam_detection_enabled", True) else "❌ Désactivé"
    embed.add_field(
        name="📊 Détections",
        value=f"**Scam:** {scam_status}\n**Spam multi-salons:** {spam_status}",
        inline=False,
    )

    threshold = config.get("spam_channel_threshold", 3)
    time_window = config.get("spam_time_window", 60)
    embed.add_field(
        name="⚡ Paramètres Spam",
        value=f"Seuil: **{threshold}** salons\nFenêtre: **{time_window}** secondes",
        inline=True,
    )

    whitelisted_roles = config.get("whitelisted_roles", []) or []
    roles_text = _format_mentions([f"<@&{role_id}>" for role_id in whitelisted_roles])
    embed.add_field(name="👥 Rôles exemptés", value=roles_text, inline=True)

    whitelisted_channels = config.get("whitelisted_channels", []) or []
    channels_text = _format_mentions([f"<#{channel_id}>" for channel_id in whitelisted_channels])
    embed.add_field(name="📝 Salons exemptés", value=channels_text, inline=True)

    custom_patterns = config.get("custom_scam_patterns", []) or []
    custom_domains = config.get("custom_scam_domains", []) or []
    embed.add_field(
        name="🔧 Personnalisations",
        value=f"**Patterns:** {len(custom_patterns)}\n**Domaines:** {len(custom_domains)}",
        inline=True,
    )

    embed.set_footer(text="Utilisez /automod action:... pour modifier la configuration")
    return embed


def _format_mentions(mentions: Sequence[str]) -> str:
    if not mentions:
        return "Aucun"

    text = "\n".join(mentions[:5])
    if len(mentions) > 5:
        text += f"\n... +{len(mentions) - 5} autres"
    return text


def build_scam_ban_dm_embed(
    *,
    guild_name: str,
    timestamp: datetime,
) -> discord.Embed:
    embed = discord.Embed(
        title="📛 Vous avez été banni(e) automatiquement",
        description="Votre message a été détecté comme un scam.",
        color=discord.Color.red(),
        timestamp=timestamp,
    )
    embed.add_field(name="Serveur", value=guild_name, inline=False)
    embed.add_field(name="Raison", value="Message de scam détecté", inline=False)
    embed.add_field(
        name="Contestation",
        value="Si vous pensez qu'il s'agit d'une erreur, contactez un administrateur.",
        inline=False,
    )
    return embed


def build_scam_log_embed(
    *,
    user_mention: str,
    user_id: int,
    user_avatar_url: str,
    channel_mention: str,
    content: str,
    timestamp: datetime,
) -> discord.Embed:
    embed = discord.Embed(
        title="🚨 Scam détecté - Ban automatique",
        color=discord.Color.red(),
        timestamp=timestamp,
    )
    embed.add_field(name="Utilisateur", value=f"{user_mention} ({user_id})", inline=False)
    embed.add_field(name="Salon", value=channel_mention, inline=True)
    embed.add_field(name="Action", value="Ban permanent", inline=True)
    embed.add_field(
        name="Contenu du message",
        value=_truncate(content, 1000),
        inline=False,
    )
    embed.set_thumbnail(url=user_avatar_url)
    return embed


def build_generic_automod_log_embed(
    *,
    user_mention: str,
    description: str | None,
    timestamp: datetime,
) -> discord.Embed:
    embed = discord.Embed(
        title="⚠️ Auto-modération",
        description=description or "Action automatique effectuée",
        color=discord.Color.orange(),
        timestamp=timestamp,
    )
    embed.add_field(name="Utilisateur", value=f"{user_mention}", inline=True)
    return embed


def build_spam_alert_embed(
    *,
    user_mention: str,
    user_id: int,
    user_avatar_url: str,
    content: str,
    channel_mentions: Sequence[str],
    timestamp: datetime,
) -> discord.Embed:
    embed = discord.Embed(
        title="⚠️ Spam multi-salons détecté",
        description="Un utilisateur a envoyé le même message dans plusieurs salons.",
        color=discord.Color.orange(),
        timestamp=timestamp,
    )
    embed.add_field(name="Utilisateur", value=f"{user_mention} ({user_id})", inline=False)
    embed.add_field(name="Contenu du message", value=_truncate(content, 500), inline=False)
    embed.add_field(
        name=f"Salons concernés ({len(channel_mentions)})",
        value="\n".join(channel_mentions[:10]) if channel_mentions else "Aucun",
        inline=False,
    )
    embed.set_thumbnail(url=user_avatar_url)
    embed.set_footer(text="Cliquez sur un bouton pour agir")
    return embed


def build_spam_ban_dm_embed(
    *,
    guild_name: str,
    timestamp: datetime,
) -> discord.Embed:
    embed = discord.Embed(
        title="📛 Vous avez été banni(e)",
        description="Vous avez été banni(e) pour spam multi-salons.",
        color=discord.Color.red(),
        timestamp=timestamp,
    )
    embed.add_field(name="Serveur", value=guild_name, inline=False)
    embed.add_field(name="Raison", value="Spam multi-salons détecté", inline=False)
    return embed


def mark_spam_alert_banned(
    embed: discord.Embed,
    *,
    moderator_mention: str,
    deleted_count: int,
) -> discord.Embed:
    embed.color = discord.Color.red()
    embed.add_field(
        name="✅ Action effectuée",
        value=f"Banni par {moderator_mention}\n{deleted_count} message(s) supprimé(s)",
        inline=False,
    )
    return embed


def mark_spam_alert_ignored(
    embed: discord.Embed,
    *,
    moderator_mention: str,
) -> discord.Embed:
    embed.color = discord.Color.light_grey()
    embed.add_field(
        name="❌ Ignoré",
        value=f"Ignoré par {moderator_mention}\nUtilisateur en whitelist pour 24h",
        inline=False,
    )
    return embed


def _truncate(content: str, limit: int) -> str:
    if len(content) <= limit:
        return content
    return content[: limit - 3] + "..."
