# cogs/voice_management/matchmaking_stats_cog.py
"""
Cog pour les commandes de statistiques et historique du matchmaking.
Commandes: /matchmaking stats, /matchmaking history, /matchmaking leaderboard
"""

import discord
from discord import app_commands
from discord.ext import commands
import logging
from typing import Optional, Literal

from .services.five_stack_service import MatchmakingService
from .services.stats_service import StatsService

logger = logging.getLogger(__name__)


class MatchmakingStats(commands.Cog):
    """
    Gère les commandes de statistiques et d'historique du matchmaking.
    """

    # Groupe de commandes /matchmaking
    matchmaking_group = app_commands.Group(
        name="matchmaking",
        description="Statistiques et historique du matchmaking"
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _get_server_id(self, guild_id: int) -> Optional[int]:
        """Récupère l'ID interne du serveur."""
        server_id = await MatchmakingService.get_server_id_by_guild_id(guild_id)
        if not server_id:
            logger.warning(f"Serveur introuvable pour la guilde={guild_id}.")
        return server_id

    # ------------------------------------------------
    # Commandes du groupe /matchmaking
    # ------------------------------------------------

    @matchmaking_group.command(name="stats", description="Voir vos statistiques de matchmaking.")
    @app_commands.describe(member="Le membre dont afficher les stats (vous par défaut).")
    async def matchmaking_stats(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None
    ) -> None:
        """
        Affiche les statistiques de matchmaking d'un joueur.
        """
        await interaction.response.defer(ephemeral=True)

        server_id = await self._get_server_id(interaction.guild.id)
        if not server_id:
            await interaction.edit_original_response(content="Serveur introuvable.")
            return

        target = member or interaction.user

        embed = await StatsService.get_player_stats_embed(target, server_id)
        await interaction.edit_original_response(embed=embed)

    @matchmaking_group.command(name="history", description="Voir votre historique de matchs.")
    @app_commands.describe(
        member="Le membre dont afficher l'historique (vous par défaut).",
        limit="Nombre de matchs à afficher (max 25)."
    )
    async def matchmaking_history(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None,
        limit: app_commands.Range[int, 1, 25] = 10
    ) -> None:
        """
        Affiche l'historique des matchs d'un joueur.
        """
        await interaction.response.defer(ephemeral=True)

        server_id = await self._get_server_id(interaction.guild.id)
        if not server_id:
            await interaction.edit_original_response(content="Serveur introuvable.")
            return

        target = member or interaction.user

        embed = await StatsService.get_match_history_embed(target, server_id, limit)
        await interaction.edit_original_response(embed=embed)

    @matchmaking_group.command(name="server", description="Voir les statistiques du serveur.")
    async def matchmaking_server(self, interaction: discord.Interaction) -> None:
        """
        Affiche les statistiques globales de matchmaking du serveur.
        """
        await interaction.response.defer(ephemeral=True)

        server_id = await self._get_server_id(interaction.guild.id)
        if not server_id:
            await interaction.edit_original_response(content="Serveur introuvable.")
            return

        embed = await StatsService.get_server_stats_embed(interaction.guild, server_id)
        await interaction.edit_original_response(embed=embed)

    @matchmaking_group.command(name="leaderboard", description="Voir le classement des joueurs.")
    @app_commands.describe(
        category="Type de classement.",
        limit="Nombre de joueurs à afficher (max 25)."
    )
    async def matchmaking_leaderboard(
        self,
        interaction: discord.Interaction,
        category: Literal["matches", "wait_time"] = "matches",
        limit: app_commands.Range[int, 5, 25] = 10
    ) -> None:
        """
        Affiche le classement des joueurs.
        """
        await interaction.response.defer(ephemeral=True)

        server_id = await self._get_server_id(interaction.guild.id)
        if not server_id:
            await interaction.edit_original_response(content="Serveur introuvable.")
            return

        embed = await StatsService.get_leaderboard_embed(
            interaction.guild, server_id, category, limit
        )
        await interaction.edit_original_response(embed=embed)

    @matchmaking_group.command(name="feedback", description="Donner un feedback pour vos matchs récents.")
    async def matchmaking_feedback(self, interaction: discord.Interaction) -> None:
        """
        Permet à l'utilisateur de donner un feedback pour ses matchs récents
        pour lesquels il n'a pas encore donné de feedback.
        """
        await interaction.response.defer(ephemeral=True)

        server_id = await self._get_server_id(interaction.guild.id)
        if not server_id:
            await interaction.edit_original_response(content="Serveur introuvable.")
            return

        # Récupérer les matchs sans feedback
        pending = await MatchmakingService.get_matches_pending_feedback(
            interaction.user.id, server_id, hours=24
        )

        if not pending:
            await interaction.edit_original_response(
                content="Vous n'avez aucun match récent en attente de feedback."
            )
            return

        # Importer la vue de feedback
        from .views.feedback_views import MatchFeedbackView

        # Envoyer un message pour chaque match (max 3)
        sent = 0
        for match in pending[:3]:
            embed = MatchFeedbackView.create_feedback_embed(
                match['match_code'],
                match['team_size']
            )
            view = MatchFeedbackView(match['id'], match['match_code'])

            if sent == 0:
                await interaction.edit_original_response(
                    content=f"Voici vos {min(len(pending), 3)} match(s) en attente de feedback:",
                    embed=embed,
                    view=view
                )
            else:
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            sent += 1

        if len(pending) > 3:
            await interaction.followup.send(
                f"Vous avez {len(pending) - 3} autre(s) match(s) en attente de feedback. "
                "Relancez la commande après avoir répondu à ceux-ci.",
                ephemeral=True
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MatchmakingStats(bot))
    logger.info("MatchmakingStats cog chargé.")
