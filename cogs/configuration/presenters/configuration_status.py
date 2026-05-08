# cogs/configuration/presenters/configuration_status.py
"""Embeds for channel and role configuration status."""

from __future__ import annotations

from typing import Mapping, Sequence

import discord


def get_channel_display_name(action_key: str, display_by_key: Mapping[str, str]) -> str:
    return display_by_key.get(action_key, action_key.replace("_", " ").capitalize())


def truncate_lines(lines: Sequence[str], limit: int = 1024) -> str:
    if not lines:
        return ""

    output: list[str] = []
    total = 0
    for line in lines:
        line_len = len(line) + (1 if output else 0)
        if total + line_len > limit - 40:
            remaining = len(lines) - len(output)
            output.append(f"... +{remaining} autres")
            break
        output.append(line)
        total += line_len
    return "\n".join(output)


def build_channels_list_embed(
    guild: discord.Guild,
    channels: Mapping[str, int],
    display_by_key: Mapping[str, str],
) -> discord.Embed:
    embed = discord.Embed(title="Salons configurés", color=discord.Color.green())
    for key in sorted(channels.keys()):
        channel_id = channels[key]
        display_name = get_channel_display_name(key, display_by_key)
        guild_channel = guild.get_channel(channel_id)
        value = guild_channel.mention if guild_channel else f"Salon introuvable (id={channel_id})"
        embed.add_field(name=f"{display_name} (`{key}`)", value=value, inline=False)
    return embed


def build_channels_status_embed(
    guild: discord.Guild,
    channels: Mapping[str, int] | None,
    predefined_actions: Sequence[tuple[str, str]],
    display_by_key: Mapping[str, str],
) -> discord.Embed:
    channels = channels or {}
    missing_actions = [key for key, _ in predefined_actions if key not in channels]

    embed = discord.Embed(title="Configuration des salons", color=discord.Color.green())
    configured_text = format_configured_channels(guild, channels, display_by_key) or "Aucun salon configuré."
    missing_text = format_missing_channel_actions(missing_actions, display_by_key) or "Rien à configurer."

    embed.add_field(name=f"Configurés ({len(channels)})", value=configured_text, inline=False)
    embed.add_field(name=f"À configurer ({len(missing_actions)})", value=missing_text, inline=False)
    embed.add_field(
        name="Astuce",
        value="`/salon action:set salon_action:<cle> channel:<salon>`",
        inline=False,
    )
    return embed


def format_configured_channels(
    guild: discord.Guild,
    channels: Mapping[str, int],
    display_by_key: Mapping[str, str],
) -> str:
    lines: list[str] = []
    for key in sorted(channels.keys()):
        channel_id = channels[key]
        display_name = get_channel_display_name(key, display_by_key)
        guild_channel = guild.get_channel(channel_id)
        if guild_channel:
            lines.append(f"- {display_name} (`{key}`): {guild_channel.mention}")
        else:
            lines.append(f"- {display_name} (`{key}`): salon introuvable (id={channel_id})")
    return truncate_lines(lines)


def format_missing_channel_actions(
    missing_actions: Sequence[str],
    display_by_key: Mapping[str, str],
) -> str:
    lines = [
        f"- {get_channel_display_name(key, display_by_key)} (`{key}`)"
        for key in missing_actions
    ]
    return truncate_lines(lines)


def build_roles_list_embed(
    guild: discord.Guild,
    roles: Mapping[str, int],
) -> discord.Embed:
    embed = discord.Embed(title="Rôles configurés", color=discord.Color.green())
    for key in sorted(roles.keys()):
        role_id = roles[key]
        guild_role = guild.get_role(role_id)
        value = guild_role.mention if guild_role else f"Rôle introuvable (id={role_id})"
        embed.add_field(name=f"`{key}`", value=value, inline=False)
    return embed


def build_roles_status_embed(
    guild: discord.Guild,
    roles: Mapping[str, int] | None,
    predefined_roles: Sequence[str],
) -> discord.Embed:
    roles = roles or {}
    missing_roles = [role_key for role_key in predefined_roles if role_key not in roles]

    embed = discord.Embed(title="Configuration des rôles", color=discord.Color.green())
    configured_text = format_configured_roles(guild, roles) or "Aucun rôle configuré."
    missing_text = format_missing_roles(missing_roles) or "Rien à configurer."

    embed.add_field(name=f"Configurés ({len(roles)})", value=configured_text, inline=False)
    embed.add_field(name=f"À configurer ({len(missing_roles)})", value=missing_text, inline=False)
    embed.add_field(
        name="Astuce",
        value="`/roles action:set role_name:<cle> role:<@role>`",
        inline=False,
    )
    return embed


def format_configured_roles(guild: discord.Guild, roles: Mapping[str, int]) -> str:
    lines: list[str] = []
    for role_key in sorted(roles.keys()):
        role_id = roles[role_key]
        guild_role = guild.get_role(role_id)
        role_mention = guild_role.mention if guild_role else f"rôle introuvable (id={role_id})"
        lines.append(f"- `{role_key}`: {role_mention}")
    return truncate_lines(lines)


def format_missing_roles(missing_roles: Sequence[str]) -> str:
    return truncate_lines([f"- `{role_key}`" for role_key in missing_roles])
