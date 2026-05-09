from __future__ import annotations

from datetime import datetime

import discord

from cogs.tournaments.services import ParsedTeamRegistration


def build_tournament_embed(
    *,
    name: str,
    registration_start: datetime,
    registration_end: datetime,
    tournament_date: datetime,
    max_teams: int,
) -> discord.Embed:
    embed = discord.Embed(title=name, color=discord.Color.blue())
    embed.description = (
        f"Inscriptions: {format_dt(registration_start)} -> {format_dt(registration_end)}\n"
        f"Date du tournoi: {format_dt(tournament_date)}\n"
        f"Places: {max_teams} equipes"
    )
    return embed


def build_team_public_message(registration: ParsedTeamRegistration) -> str:
    players = "\n".join(f"- <@{discord_id}>" for discord_id in registration.player_discord_ids)
    substitutes = "\n".join(f"- <@{discord_id}>" for discord_id in registration.substitute_discord_ids)
    parts = [f"**Equipe:** {registration.team_name}", "**Joueurs:**", players]
    if substitutes:
        parts.extend(["**Remplacants:**", substitutes])
    if registration.coach_discord_id:
        parts.extend(["**Coach:**", f"- <@{registration.coach_discord_id}>"])
    return "\n".join(parts)


def format_dt(value: datetime) -> str:
    return value.strftime("%d/%m/%Y %H:%M")
