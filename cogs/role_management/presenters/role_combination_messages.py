from __future__ import annotations

import discord

from cogs.role_management.services.role_combination_service import RoleCombinationInfo


def build_role_combinations_embed(
    guild: discord.Guild,
    combinations: list[RoleCombinationInfo],
) -> discord.Embed:
    embed = discord.Embed(
        title="Combinaisons de roles configurees",
        color=discord.Color.green(),
    )
    if not combinations:
        embed.description = "Aucune combinaison de roles configuree."
        return embed

    for combination in combinations:
        primary = _format_role(guild, combination.primary_role_id)
        secondary = _format_role(guild, combination.secondary_role_id)
        combined = _format_role(guild, combination.combined_role_id)
        embed.add_field(name=f"{primary} + {secondary}", value=f"-> {combined}", inline=False)
    return embed


def _format_role(guild: discord.Guild, role_id: int) -> str:
    role = guild.get_role(role_id)
    return role.mention if role else f"Role manquant ({role_id})"
