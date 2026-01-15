#cogs\voice_management\team_views.py

import discord
import logging
from typing import Any

from cogs.voice_management.services.five_stack_service import MatchmakingService
from cogs.ranking.services.assign_rank_service import valorant_account_linked

logger = logging.getLogger(__name__)


class BaseLeaveTeamView(discord.ui.View):
    """Base view providing the logic to leave a team."""

    EMPTY_TEAM_MESSAGE: str = (
        "Vous avez quitté l'équipe. Elle est vide et va être supprimée."
    )

    def __init__(self, cog: Any, code: str) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.code = code

    async def handle_leave_team(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        server_id = await self.cog._get_server_id(interaction.guild.id)
        if not server_id:
            await interaction.followup.send(
                content="Serveur introuvable.",
                ephemeral=True,
            )
            return
        if not await valorant_account_linked(interaction.user.id):
            await interaction.followup.send(
                content="Veuillez lier votre compte Valorant avant de rejoindre l'équipe.",
                ephemeral=True,
            )
            return

        team = await MatchmakingService.get_team(self.code, server_id)
        if not team:
            await interaction.followup.send(
                content="Équipe introuvable ou expirée.",
                ephemeral=True,
            )
            return

        success = await MatchmakingService.remove_member_from_team(
            self.code, interaction.user.id, server_id
        )
        if not success:
            await interaction.followup.send(
                content="Erreur lors de la tentative de quitter l'équipe.",
                ephemeral=True,
            )
            return

        members = await MatchmakingService.get_team_members(self.code, server_id)

        if team.get("leader_id") == interaction.user.id:
            if members:
                new_leader_id = members[0]
                await MatchmakingService.update_team_leader(self.code, new_leader_id, server_id)
                logger.info(
                    f"Transfert du lead de {interaction.user.id} vers {new_leader_id} pour l'équipe {self.code}."
                )
            else:
                logger.info("Le leader quitte et l'équipe est vide => suppression imminente.")

        if not members:
            logger.info(
                f"L'équipe '{self.code}' est vide. Suppression des ressources et de la BDD."
            )
            await interaction.followup.send(
                content=self.EMPTY_TEAM_MESSAGE,
                ephemeral=True,
            )
            team_data = await MatchmakingService.get_team(self.code, server_id)
            if team_data:
                await self.cog.delete_team_resources(team_data)
                await MatchmakingService.delete_team(self.code, server_id)
        else:
            await self.cog.update_team_thread(self.code, server_id)
            await interaction.followup.send(
                content="Vous avez quitté l'équipe.",
                ephemeral=True,
            )


class TeamForumJoinButtonView(BaseLeaveTeamView):
    """
    Vue placée dans le post forum pour les équipes publiques.
    
    Contient deux boutons :
      - "Rejoindre l'équipe" : permet à l'utilisateur de rejoindre l'équipe.
      - "Quitter l'équipe" : permet de quitter l'équipe.
    """
    EMPTY_TEAM_MESSAGE = (
        "Vous avez quitté l'équipe. L'équipe est désormais vide et va être supprimée."
    )

    def __init__(self, cog: Any, code: str) -> None:
        super().__init__(cog, code)

        # Bouton "Rejoindre l'équipe"
        join_button = discord.ui.Button(
            label="Rejoindre l'équipe",
            style=discord.ButtonStyle.success,
            custom_id=f"join_team_{self.code}"
        )
        join_button.callback = self.join_team_button_callback
        self.add_item(join_button)

        # Bouton "Quitter l'équipe"
        leave_button = discord.ui.Button(
            label="Quitter l'équipe",
            style=discord.ButtonStyle.danger,
            custom_id=f"leave_team_{self.code}"
        )
        leave_button.callback = self.leave_team_button_callback
        self.add_item(leave_button)

    async def join_team_button_callback(self, interaction: discord.Interaction) -> None:
        """
        Callback pour rejoindre une équipe publique.
        
        Vérifie que l'équipe existe, que sa visibilité est publique,
        que l'utilisateur n'est pas déjà dans une autre équipe, que l'équipe n'est pas pleine,
        et que la région de l'utilisateur correspond à celle du leader.
        En cas de succès, ajoute le joueur et met à jour le thread.
        Si l'équipe atteint 5 membres, le salon vocal est créé.
        """
        await interaction.response.defer(ephemeral=True)
        server_id = await self.cog._get_server_id(interaction.guild.id)
        if not server_id:
            await interaction.followup.send(
                content="Serveur introuvable.",
                ephemeral=True,
            )
            return
        if not await valorant_account_linked(interaction.user.id):
            await interaction.followup.send(
                content="Veuillez lier votre compte Valorant avant de rejoindre l'équipe.",
                ephemeral=True,
            )
            return

        team = await MatchmakingService.get_team(self.code, server_id)
        if not team:
            await interaction.followup.send(
                content="Équipe introuvable ou expirée.",
                ephemeral=True
            )
            return

        if team.get("visibility") != "public":
            await interaction.followup.send(
                content="Cette équipe est privée et ne peut pas être rejointe via ce bouton.",
                ephemeral=True
            )
            return

        # Vérifier si l'utilisateur est déjà membre d'une autre équipe
        if await MatchmakingService.is_user_in_any_team(interaction.user.id, server_id):
            await interaction.followup.send(
                content="Vous êtes déjà membre d'une autre équipe.",
                ephemeral=True
            )
            return

        # Vérifier si l'équipe est complète
        members = await MatchmakingService.get_team_members(self.code, server_id)
        if len(members) >= 5:
            await interaction.followup.send(
                content="Cette équipe est déjà complète (5 membres).",
                ephemeral=True
            )
            return

        # Vérification des informations Valorant (région)
        leader_info = await MatchmakingService.get_user_info(team["leader_id"])
        user_info = await MatchmakingService.get_user_info(interaction.user.id)
        if not leader_info or not user_info:
            await interaction.followup.send(
                content="Infos Valorant manquantes (leader ou vous).",
                ephemeral=True
            )
            return
        if user_info.get("region") != leader_info.get("region"):
            await interaction.followup.send(
                content="Votre région est différente de celle du leader.",
                ephemeral=True
            )
            return

        # Ajouter le joueur à l'équipe
        if not await MatchmakingService.add_member_to_team(self.code, interaction.user.id, server_id):
            await interaction.followup.send(
                content="Erreur lors de l'ajout à l'équipe.",
                ephemeral=True
            )
            return

        # Mettre à jour le thread pour refléter le changement
        await self.cog.update_team_thread(self.code, server_id)
        await interaction.followup.send(
            content="Vous avez rejoint l'équipe !",
            ephemeral=True
        )

        # Si l'équipe atteint 5 membres, créer le salon vocal
        if len(members) + 1 == 5:
            await self.cog.create_voice_channel_and_invite(team)

    async def leave_team_button_callback(self, interaction: discord.Interaction) -> None:
        """Callback pour quitter l'équipe depuis une vue publique."""
        await self.handle_leave_team(interaction)


class TeamForumPrivateView(BaseLeaveTeamView):
    """
    Vue pour un post forum d'équipe privée.
    
    Ne contient qu'un seul bouton permettant de quitter l'équipe.
    """
    def __init__(self, cog: Any, code: str) -> None:
        super().__init__(cog, code)

        leave_button = discord.ui.Button(
            label="Quitter l'équipe",
            style=discord.ButtonStyle.danger,
            custom_id=f"leave_private_{self.code}"
        )
        leave_button.callback = self.leave_team_button_callback
        self.add_item(leave_button)

    async def leave_team_button_callback(self, interaction: discord.Interaction) -> None:
        """Callback pour quitter l'équipe depuis une vue privée."""
        await self.handle_leave_team(interaction)
