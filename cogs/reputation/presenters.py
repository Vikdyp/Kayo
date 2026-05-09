from __future__ import annotations

import discord

from database.services.reputation_service import ReputationSummary, UserProfileInfo


def reputation_ratio(summary: ReputationSummary) -> float:
    return (summary.recommendations + 1) / (summary.reports + 1)


def build_reputation_summary_embed(member: discord.Member, summary: ReputationSummary) -> discord.Embed:
    ratio = reputation_ratio(summary)
    embed = discord.Embed(
        title=f"Profil resume de {member.display_name}",
        color=discord.Color.blue(),
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="Signalements", value=str(summary.reports), inline=True)
    embed.add_field(name="Recommandations", value=str(summary.recommendations), inline=True)
    embed.add_field(name="Ratio", value=f"{ratio:.2f}", inline=True)
    return embed


def build_full_profile_embed(
    *,
    member: discord.Member,
    summary: ReputationSummary,
    profile: UserProfileInfo,
    rank: str,
    language: str,
    platform: str,
) -> discord.Embed:
    tracker = profile.valorant_tracker or "Aucun"
    tracker_value = "Aucun" if tracker == "Aucun" else f"[Voir le tracker]({tracker})"

    embed = discord.Embed(
        title=f"Profil de {member.display_name}",
        description="Informations du joueur.",
        color=discord.Color.green(),
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="Signalements", value=f"`{summary.reports}`", inline=True)
    embed.add_field(name="Recommandations", value=f"`{summary.recommendations}`", inline=True)
    embed.add_field(name="Ratio", value=f"`{reputation_ratio(summary):.2f}`", inline=True)
    embed.add_field(name="Genre", value=profile.genre or "Non specifie", inline=True)
    embed.add_field(name="Equipe", value=profile.lft or "Rien", inline=True)
    embed.add_field(name="Rang actuel", value=rank, inline=True)
    embed.add_field(name="Langue & plateforme", value=f"{language}\n{platform}", inline=True)
    embed.add_field(name="Valorant Tracker", value=tracker_value, inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True)
    embed.add_field(name="Note personnelle", value=profile.note or "Aucune", inline=False)
    return embed
