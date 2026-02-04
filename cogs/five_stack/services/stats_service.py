# cogs/voice_management/services/stats_service.py
"""
Service pour les statistiques de matchmaking.
Fournit des méthodes pour récupérer et formater les statistiques des joueurs et du serveur.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any

import discord

from .five_stack_service import MatchmakingService

logger = logging.getLogger(__name__)


class StatsService:
    """
    Service pour récupérer et formater les statistiques de matchmaking.
    """

    @staticmethod
    async def get_player_stats_embed(
        member: discord.Member,
        server_id: int
    ) -> discord.Embed:
        """
        Crée un embed avec les statistiques d'un joueur.

        Args:
            member: Membre Discord
            server_id: ID du serveur

        Returns:
            Embed Discord formaté
        """
        stats = await MatchmakingService.get_player_stats(member.id, server_id)

        embed = discord.Embed(
            title=f"Statistiques Matchmaking",
            color=discord.Color.blue()
        )
        embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)

        if not stats:
            embed.description = "Aucune statistique disponible. Participez à des matchs pour commencer !"
            return embed

        # Stats principales
        total_matches = stats.get('total_matches', 0)
        total_wait = stats.get('total_wait_time_seconds', 0)
        solo_matches = stats.get('matches_as_solo', 0)
        group_matches = stats.get('matches_in_group', 0)
        preferred_role = stats.get('preferred_role', 'Non défini')
        last_match = stats.get('last_match_at')

        # Calculer le temps d'attente moyen
        avg_wait = total_wait // total_matches if total_matches > 0 else 0
        avg_wait_str = StatsService._format_duration(avg_wait)

        # Ratio solo/groupe
        if total_matches > 0:
            solo_percent = (solo_matches / total_matches) * 100
            group_percent = (group_matches / total_matches) * 100
        else:
            solo_percent = 0
            group_percent = 0

        embed.add_field(
            name="Total Matchs",
            value=f"**{total_matches}**",
            inline=True
        )
        embed.add_field(
            name="Temps d'attente moyen",
            value=f"**{avg_wait_str}**",
            inline=True
        )
        embed.add_field(
            name="Rôle préféré",
            value=f"**{preferred_role.capitalize() if preferred_role else 'Non défini'}**",
            inline=True
        )

        embed.add_field(
            name="Matchs Solo",
            value=f"{solo_matches} ({solo_percent:.0f}%)",
            inline=True
        )
        embed.add_field(
            name="Matchs en Groupe",
            value=f"{group_matches} ({group_percent:.0f}%)",
            inline=True
        )

        if last_match:
            if last_match.tzinfo is None:
                last_match = last_match.replace(tzinfo=timezone.utc)
            embed.add_field(
                name="Dernier match",
                value=f"<t:{int(last_match.timestamp())}:R>",
                inline=True
            )

        # Temps total passé en attente
        total_wait_str = StatsService._format_duration(total_wait)
        embed.set_footer(text=f"Temps total en file d'attente: {total_wait_str}")

        return embed

    @staticmethod
    async def get_match_history_embed(
        member: discord.Member,
        server_id: int,
        limit: int = 10
    ) -> discord.Embed:
        """
        Crée un embed avec l'historique des matchs d'un joueur.

        Args:
            member: Membre Discord
            server_id: ID du serveur
            limit: Nombre de matchs à afficher

        Returns:
            Embed Discord formaté
        """
        matches = await MatchmakingService.get_player_match_history(member.id, server_id, limit)

        embed = discord.Embed(
            title=f"Historique des Matchs",
            color=discord.Color.green()
        )
        embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)

        if not matches:
            embed.description = "Aucun match dans l'historique."
            return embed

        for i, match in enumerate(matches, 1):
            created_at = match.get('created_at')
            if created_at and created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)

            team_size = match.get('team_size', '?')
            quality = match.get('match_quality_score', 0)
            elo_spread = match.get('elo_spread', 0)
            avg_elo = match.get('avg_elo', 0)

            # Déterminer l'emoji de qualité
            if quality >= 0.8:
                quality_emoji = "🌟"
            elif quality >= 0.6:
                quality_emoji = "✅"
            elif quality >= 0.4:
                quality_emoji = "⚠️"
            else:
                quality_emoji = "❌"

            timestamp_str = f"<t:{int(created_at.timestamp())}:d>" if created_at else "?"

            embed.add_field(
                name=f"{i}. Match {match.get('match_code', '?')}",
                value=(
                    f"**Date:** {timestamp_str}\n"
                    f"**Taille:** {team_size}v{team_size} | **ELO moyen:** {avg_elo}\n"
                    f"**Qualité:** {quality_emoji} {quality:.0%} | **Écart ELO:** {elo_spread}"
                ),
                inline=False
            )

        embed.set_footer(text=f"Affichage des {len(matches)} derniers matchs")

        return embed

    @staticmethod
    async def get_server_stats_embed(
        guild: discord.Guild,
        server_id: int
    ) -> discord.Embed:
        """
        Crée un embed avec les statistiques globales du serveur.

        Args:
            guild: Serveur Discord
            server_id: ID du serveur interne

        Returns:
            Embed Discord formaté
        """
        stats = await MatchmakingService.get_server_matchmaking_stats(server_id)

        embed = discord.Embed(
            title="Statistiques Matchmaking du Serveur",
            color=discord.Color.gold()
        )
        embed.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else None)

        if not stats:
            embed.description = "Aucune statistique disponible pour ce serveur."
            return embed

        total_matches = stats.get('total_matches', 0)
        total_players = stats.get('unique_players', 0)
        avg_quality = stats.get('avg_quality_score', 0)
        avg_wait = stats.get('avg_wait_time_seconds', 0)
        matches_today = stats.get('matches_today', 0)
        matches_week = stats.get('matches_this_week', 0)

        embed.add_field(
            name="Total Matchs",
            value=f"**{total_matches}**",
            inline=True
        )
        embed.add_field(
            name="Joueurs Uniques",
            value=f"**{total_players}**",
            inline=True
        )
        embed.add_field(
            name="Qualité Moyenne",
            value=f"**{avg_quality:.0%}**",
            inline=True
        )

        embed.add_field(
            name="Matchs Aujourd'hui",
            value=f"**{matches_today}**",
            inline=True
        )
        embed.add_field(
            name="Matchs Cette Semaine",
            value=f"**{matches_week}**",
            inline=True
        )
        embed.add_field(
            name="Attente Moyenne",
            value=f"**{StatsService._format_duration(int(avg_wait))}**",
            inline=True
        )

        # Distribution des tailles d'équipe
        size_dist = stats.get('team_size_distribution', {})
        if size_dist:
            dist_text = "\n".join([
                f"**{size}v{size}:** {count} matchs"
                for size, count in sorted(size_dist.items())
            ])
            embed.add_field(
                name="Distribution par Taille",
                value=dist_text or "N/A",
                inline=False
            )

        return embed

    @staticmethod
    async def get_leaderboard_embed(
        guild: discord.Guild,
        server_id: int,
        category: str = "matches",
        limit: int = 10
    ) -> discord.Embed:
        """
        Crée un embed avec le classement des joueurs.

        Args:
            guild: Serveur Discord
            server_id: ID du serveur
            category: Catégorie de classement (matches, wait_time)
            limit: Nombre de joueurs à afficher

        Returns:
            Embed Discord formaté
        """
        leaderboard = await MatchmakingService.get_leaderboard(server_id, category, limit)

        title_map = {
            'matches': "Classement - Plus de Matchs",
            'wait_time': "Classement - Plus Patient (Temps d'attente)"
        }

        embed = discord.Embed(
            title=title_map.get(category, "Classement"),
            color=discord.Color.purple()
        )

        if not leaderboard:
            embed.description = "Aucune donnée disponible pour ce classement."
            return embed

        for i, entry in enumerate(leaderboard, 1):
            # Emoji pour le podium
            if i == 1:
                medal = "🥇"
            elif i == 2:
                medal = "🥈"
            elif i == 3:
                medal = "🥉"
            else:
                medal = f"**{i}.**"

            member = guild.get_member(entry['discord_id'])
            name = member.display_name if member else f"Utilisateur {entry['discord_id']}"

            if category == 'matches':
                value = f"{entry['total_matches']} matchs"
            else:  # wait_time
                value = StatsService._format_duration(entry['total_wait_time_seconds'])

            embed.add_field(
                name=f"{medal} {name}",
                value=value,
                inline=False
            )

        return embed

    @staticmethod
    def _format_duration(seconds: int) -> str:
        """
        Formate une durée en secondes en chaîne lisible.

        Args:
            seconds: Durée en secondes

        Returns:
            Chaîne formatée (ex: "1h 23m" ou "5m 30s")
        """
        if seconds < 60:
            return f"{seconds}s"

        minutes = seconds // 60
        remaining_seconds = seconds % 60

        if minutes < 60:
            if remaining_seconds > 0:
                return f"{minutes}m {remaining_seconds}s"
            return f"{minutes}m"

        hours = minutes // 60
        remaining_minutes = minutes % 60

        if hours < 24:
            if remaining_minutes > 0:
                return f"{hours}h {remaining_minutes}m"
            return f"{hours}h"

        days = hours // 24
        remaining_hours = hours % 24

        if remaining_hours > 0:
            return f"{days}j {remaining_hours}h"
        return f"{days}j"
