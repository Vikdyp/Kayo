from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import discord

from database.services.scrims_service import ScrimInfo

PARIS_TZ = ZoneInfo("Europe/Paris")


def build_scrim_creation_message() -> str:
    return "Cliquez sur le bouton ci-dessous pour creer un scrim :"


def build_scrim_embed(scrim: ScrimInfo) -> discord.Embed:
    creator = f"<@{scrim.creator_discord_id}>" if scrim.creator_discord_id else "un membre"
    embed = discord.Embed(title=f"Scrim de {creator}", color=discord.Color.blue())
    embed.add_field(name="Map", value=scrim.map_name, inline=True)
    embed.add_field(name="Rang", value=scrim.rank_name, inline=True)
    embed.add_field(name="Date et heure", value=format_dt(scrim.scheduled_at), inline=True)
    if scrim.notes:
        embed.add_field(name="Autres precisions", value=scrim.notes, inline=False)
    embed.add_field(name="Equipe 1", value=format_team(scrim.team1_discord_ids), inline=False)
    embed.add_field(name="Equipe 2", value=format_team(scrim.team2_discord_ids), inline=False)
    return embed


def format_team(discord_ids: tuple[int, ...]) -> str:
    if not discord_ids:
        return "En attente..."
    return "\n".join(f"<@{discord_id}>" for discord_id in discord_ids)


def format_dt(value: datetime) -> str:
    return value.astimezone(PARIS_TZ).strftime("%d/%m/%Y a %H:%M")


def join_status_message(status: str, *, team_label: str) -> str:
    if status == "joined":
        return f"Inscription validee pour {team_label}."
    if status == "already_registered":
        return "Vous etes deja inscrit dans une equipe."
    if status == "full":
        return f"{team_label} est deja complete."
    return "Scrim introuvable ou termine."


def leave_status_message(status: str) -> str:
    if status == "left":
        return "Vous avez quitte le scrim."
    if status == "not_registered":
        return "Vous n'etes pas inscrit dans ce scrim."
    return "Scrim introuvable ou termine."
