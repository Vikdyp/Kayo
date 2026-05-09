from __future__ import annotations

from typing import Mapping, Sequence

import discord


def build_game_roles_embed(role_counts: Mapping[str, int]) -> discord.Embed:
    embed = discord.Embed(
        title="Selectionnez votre role Valorant",
        description=(
            "Choisissez le role que vous souhaitez jouer. "
            "Un seul role Valorant peut etre actif a la fois."
        ),
        color=discord.Color.green(),
    )
    roles_display = "\n".join(
        f"**{role_name.capitalize()}**: {count} membre(s)"
        for role_name, count in role_counts.items()
    )
    embed.add_field(
        name="Repartition des roles",
        value=roles_display or "Aucun role configure.",
        inline=False,
    )
    embed.set_footer(text="Vous pouvez changer de role a tout moment.")
    return embed


def build_language_roles_embed() -> discord.Embed:
    return discord.Embed(
        title="Choisissez votre langue",
        description="Cliquez sur le bouton correspondant pour ajouter ou retirer le role.",
        color=discord.Color.blue(),
    )


def format_missing_config_message(keys: Sequence[str]) -> str:
    return "Roles non configures avec /roles: " + ", ".join(f"`{key}`" for key in keys)


def format_missing_discord_roles_message(keys: Sequence[str]) -> str:
    return "Roles introuvables sur Discord: " + ", ".join(f"`{key}`" for key in keys)


def format_role_selection_result(
    *,
    added_mention: str | None,
    removed_mentions: Sequence[str],
    already_selected_mention: str | None = None,
) -> str:
    if already_selected_mention:
        return f"Vous possedez deja le role {already_selected_mention}."

    messages: list[str] = []
    if removed_mentions:
        messages.append("Role(s) retire(s): " + ", ".join(removed_mentions) + ".")
    if added_mention:
        messages.append(f"Role ajoute: {added_mention}.")
    if not messages:
        return "Aucun changement de role."
    return "\n".join(messages)
