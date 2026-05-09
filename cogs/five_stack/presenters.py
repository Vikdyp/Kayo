from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

import discord

from database.services.five_stack_service import FiveStackMatchBundle, FiveStackTeamInfo


def build_queue_embed(entries: Iterable[object]) -> discord.Embed:
    rows = tuple(entries)
    total_players = sum(len(entry.all_member_ids) for entry in rows)
    solo = sum(1 for entry in rows if entry.entry_type == 1)
    groups = len(rows) - solo

    embed = discord.Embed(
        title="Matchmaking Five Stack",
        description="Rejoignez la queue en solo ou avec votre equipe.",
        color=discord.Color.blurple(),
    )
    embed.add_field(name="Joueurs en attente", value=str(total_players), inline=True)
    embed.add_field(name="Solo", value=str(solo), inline=True)
    embed.add_field(name="Groupes", value=str(groups), inline=True)

    if rows:
        lines = []
        for entry in rows[:10]:
            size = "any" if entry.desired_team_size == 0 else str(entry.desired_team_size)
            lines.append(
                f"<@{entry.discord_member_id}> - {entry.entry_type} joueur(s), "
                f"{entry.language}/{entry.region}/{entry.platform}, cible {size}"
            )
        if len(rows) > 10:
            lines.append(f"... +{len(rows) - 10} entree(s)")
        embed.add_field(name="Queue", value="\n".join(lines), inline=False)
    else:
        embed.add_field(name="Queue", value="Aucun joueur en attente.", inline=False)

    embed.set_footer(text="La queue passe en any apres 5 min et expire apres 10 min.")
    return embed


def build_role_counters_embed(counts: dict[str, int]) -> discord.Embed:
    embed = discord.Embed(title="Compteurs de roles Five Stack", color=discord.Color.green())
    for role, count in counts.items():
        embed.add_field(name=role, value=str(count), inline=True)
    return embed


def build_team_embed(team: FiveStackTeamInfo) -> discord.Embed:
    visibility = "publique" if team.team.visibility == "public" else "privee"
    members = "\n".join(f"<@{member_id}>" for member_id in team.member_ids) or "Aucun membre"
    embed = discord.Embed(
        title=f"Equipe {team.team.code}",
        description=f"Equipe {visibility} creee pour le matchmaking.",
        color=discord.Color.orange(),
    )
    embed.add_field(name="Leader", value=f"<@{team.team.leader_discord_id}>", inline=True)
    embed.add_field(name="Membres", value=f"{len(team.member_ids)}/5", inline=True)
    embed.add_field(name="Liste", value=members, inline=False)
    return embed


def team_status_message(status: str, *, code: str | None = None) -> str:
    messages = {
        "created": f"Equipe creee: `{code}`.",
        "joined": "Vous avez rejoint l'equipe.",
        "left": "Vous avez quitte l'equipe.",
        "kicked": "Membre retire de l'equipe.",
        "deleted": "Equipe supprimee.",
        "already_in_team": "Vous etes deja dans cette equipe.",
        "already_in_other_team": "Vous etes deja dans une autre equipe.",
        "not_in_team": "Vous n'etes dans aucune equipe.",
        "not_found": "Equipe introuvable.",
        "not_leader": "Seul le leader de l'equipe peut faire cette action.",
        "cannot_kick_self": "Utilisez `/team leave` pour quitter votre equipe.",
        "member_not_in_team": "Ce membre n'est pas dans cette equipe.",
        "full": "Cette equipe est complete.",
        "missing_valorant": "Compte Valorant non lie ou profil incomplet.",
        "invalid_visibility": "Visibilite invalide.",
        "code_collision": "Impossible de generer un code unique, reessayez.",
    }
    return messages.get(status, "Action terminee.")


def queue_status_message(status: str) -> str:
    messages = {
        "joined": "Vous avez rejoint la queue.",
        "left": "Vous avez quitte la queue.",
        "missing_valorant": "Vous devez lier votre compte Valorant avant de rejoindre la queue.",
        "missing_team": "Vous devez etre leader d'une equipe pour rejoindre en equipe.",
        "invalid_size": "Taille de match invalide.",
    }
    return messages.get(status, "Action terminee.")


def build_player_stats_embed(member: discord.abc.User, stats) -> discord.Embed:
    embed = discord.Embed(title=f"Stats matchmaking - {member.display_name}", color=discord.Color.blurple())
    if stats is None:
        embed.description = "Aucun match enregistre."
        return embed

    avg_wait = stats.total_wait_time_seconds // stats.total_matches if stats.total_matches else 0
    embed.add_field(name="Matchs", value=str(stats.total_matches), inline=True)
    embed.add_field(name="Solo", value=str(stats.matches_as_solo), inline=True)
    embed.add_field(name="Groupe", value=str(stats.matches_in_group), inline=True)
    embed.add_field(name="Attente moyenne", value=f"{avg_wait}s", inline=True)
    embed.add_field(name="Role prefere", value=stats.preferred_role or "N/A", inline=True)
    if stats.last_match_at:
        embed.add_field(name="Dernier match", value=_format_dt(stats.last_match_at), inline=True)
    return embed


def build_server_stats_embed(guild: discord.Guild, stats: dict) -> discord.Embed:
    embed = discord.Embed(title=f"Stats matchmaking - {guild.name}", color=discord.Color.green())
    embed.add_field(name="Matchs", value=str(int(stats.get("total_matches", 0))), inline=True)
    embed.add_field(name="Aujourd'hui", value=str(int(stats.get("matches_today", 0))), inline=True)
    embed.add_field(name="Cette semaine", value=str(int(stats.get("matches_this_week", 0))), inline=True)
    embed.add_field(name="Qualite moyenne", value=f"{float(stats.get('avg_quality_score', 0)):.2f}", inline=True)
    embed.add_field(name="Elo spread moyen", value=str(int(float(stats.get("avg_elo_spread", 0)))), inline=True)
    distribution = stats.get("team_size_distribution", {}) or {}
    if distribution:
        embed.add_field(
            name="Tailles",
            value="\n".join(f"{size}v{size}: {count}" for size, count in sorted(distribution.items())),
            inline=False,
        )
    return embed


def build_leaderboard_embed(guild: discord.Guild, rows: Iterable[object], *, category: str) -> discord.Embed:
    title = "Leaderboard matchs" if category == "matches" else "Leaderboard attente"
    embed = discord.Embed(title=f"{title} - {guild.name}", color=discord.Color.gold())
    lines = []
    for index, row in enumerate(rows, start=1):
        value = row.total_matches if category == "matches" else f"{row.total_wait_time_seconds}s"
        lines.append(f"{index}. <@{row.discord_member_id}> - {value}")
    embed.description = "\n".join(lines) if lines else "Aucune stat."
    return embed


def build_match_history_embed(member: discord.abc.User, bundles: Iterable[FiveStackMatchBundle]) -> discord.Embed:
    embed = discord.Embed(title=f"Historique matchmaking - {member.display_name}", color=discord.Color.blurple())
    lines = []
    for bundle in bundles:
        lines.append(
            f"`{bundle.match.match_code}` - {bundle.match.team_size}v{bundle.match.team_size} "
            f"- {_format_dt(bundle.match.created_at)}"
        )
    embed.description = "\n".join(lines) if lines else "Aucun match recent."
    return embed


def build_global_match_history_embed(rows: Iterable[object]) -> discord.Embed:
    embed = discord.Embed(title="Historique matchmaking serveur", color=discord.Color.blurple())
    lines = []
    for match in rows:
        lines.append(
            f"`{match.match_code}` - {match.team_size}v{match.team_size} "
            f"- qualite {match.quality_score:.2f} - {_format_dt(match.created_at)}"
        )
    embed.description = "\n".join(lines) if lines else "Aucun match recent."
    return embed


def _format_dt(value: datetime) -> str:
    dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return discord.utils.format_dt(dt, "R")
