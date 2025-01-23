#cogs\voice_management\team_views.py
import discord
import logging

from cogs.voice_management.services.five_stack_service import MatchmakingService

logger = logging.getLogger(__name__)


class TeamForumJoinButtonView(discord.ui.View):
    """
    Vue placée dans le post forum pour les équipes publiques :
    - Bouton "Rejoindre l'équipe"
    - Bouton "Quitter l'équipe"
    """
    def __init__(self, cog, code: str):
        super().__init__(timeout=None)
        self.cog = cog       # Référence au Cog (TeamManager)
        self.code = code     # Code unique de l'équipe

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

    async def join_team_button_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        team = await MatchmakingService.get_team(self.code)
        if not team:
            await interaction.followup.send(
                content="Équipe introuvable ou expirée.",
                ephemeral=True
            )
            return

        if team["visibility"] != "public":
            await interaction.followup.send(
                content="Cette équipe est privée et ne peut pas être rejointe via ce bouton.",
                ephemeral=True
            )
            return

        # Vérifier si l'utilisateur est déjà dans une autre équipe
        existing_code = await MatchmakingService.is_user_in_any_team(interaction.user.id)
        if existing_code:
            await interaction.followup.send(
                content="Vous êtes déjà membre d'une autre équipe.",
                ephemeral=True
            )
            return

        # Vérifier si l'équipe est pleine
        members = await MatchmakingService.get_team_members(self.code)
        if len(members) >= 5:
            await interaction.followup.send(
                content="Cette équipe est déjà complète (5 membres).",
                ephemeral=True
            )
            return

        # Vérification Valorant (région)
        leader_info = await MatchmakingService.get_user_info(team["leader_id"])
        user_info = await MatchmakingService.get_user_info(interaction.user.id)
        if not leader_info or not user_info:
            await interaction.followup.send(
                content="Infos Valorant manquantes (leader ou vous).",
                ephemeral=True
            )
            return
        if user_info["region"] != leader_info["region"]:
            await interaction.followup.send(
                content="Votre région est différente de celle du leader.",
                ephemeral=True
            )
            return

        # Ajouter ce joueur à l'équipe
        ok = await MatchmakingService.add_member_to_team(self.code, interaction.user.id)
        if not ok:
            await interaction.followup.send(
                content="Erreur lors de l'ajout à l'équipe.",
                ephemeral=True
            )
            return

        # Mettre à jour le thread (titre, liste, etc.)
        await self.cog.update_team_thread(self.code)
        await interaction.followup.send(
            content="Vous avez rejoint l'équipe !",
            ephemeral=True
        )

        # Vérifier si on atteint 5
        if len(members) + 1 == 5:
            # Créer le salon vocal
            await self.cog.create_voice_channel_and_invite(team)

    async def leave_team_button_callback(self, interaction: discord.Interaction):
        """
        Callback pour "Quitter l'équipe".
        On supprime le membre de l'équipe, on met à jour,
        on supprime l'équipe si elle devient vide (et on supprime de la BDD).
        Si c'était le leader, on transfère le lead à un autre membre.
        """
        await interaction.response.defer(ephemeral=True)

        # 1) Récupérer l'équipe avant de retirer le membre
        team = await MatchmakingService.get_team(self.code)
        if not team:
            await interaction.followup.send(
                content="Équipe introuvable ou expirée.",
                ephemeral=True
            )
            return

        # 2) Retirer le membre
        success = await MatchmakingService.remove_member_from_team(self.code, interaction.user.id)
        if success:
            # 3) Récupérer les membres restants
            members = await MatchmakingService.get_team_members(self.code)

            # 4) Si le joueur qui quitte est le leader, transférer le leadership
            if team["leader_id"] == interaction.user.id:
                if len(members) > 0:
                    new_leader_id = members[0]  # Choix arbitraire : le premier de la liste
                    await MatchmakingService.update_team_leader(self.code, new_leader_id)
                    logger.info(f"Transfert du lead de {interaction.user.id} vers {new_leader_id} pour l'équipe {self.code}.")
                else:
                    logger.info(f"Le leader quitte et l'équipe est vide => suppression imminente.")

            if len(members) == 0:
                # Équipe vide => suppression
                logger.info(f"L'équipe '{self.code}' est vide. Suppression des ressources + DB.")

                # 1) Répondre à l'utilisateur
                await interaction.followup.send(
                    content="Vous avez quitté l'équipe. L'équipe est désormais vide et va être supprimée.",
                    ephemeral=True
                )

                # 2) Supprimer les ressources Discord
                team_data = await MatchmakingService.get_team(self.code)
                if team_data:
                    await self.cog.delete_team_resources(team_data)

                    # 3) Supprimer dans la BDD
                    await MatchmakingService.delete_team(self.code)

            else:
                # Mettre à jour le thread
                await self.cog.update_team_thread(self.code)
                await interaction.followup.send(
                    content="Vous avez quitté l'équipe.",
                    ephemeral=True
                )
        else:
            await interaction.followup.send(
                content="Erreur lors de la tentative de quitter l'équipe.",
                ephemeral=True
            )


class TeamForumPrivateView(discord.ui.View):
    """
    Vue pour un post forum d'équipe privée :
    - Un seul bouton "Quitter l'équipe"
    """
    def __init__(self, cog, code: str):
        super().__init__(timeout=None)
        self.cog = cog
        self.code = code

        leave_button = discord.ui.Button(
            label="Quitter l'équipe",
            style=discord.ButtonStyle.danger,
            custom_id=f"leave_private_{self.code}"
        )
        leave_button.callback = self.leave_team_button_callback
        self.add_item(leave_button)

    async def leave_team_button_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # 1) Récupérer l'équipe
        team = await MatchmakingService.get_team(self.code)
        if not team:
            await interaction.followup.send(
                content="Équipe introuvable ou expirée.",
                ephemeral=True
            )
            return

        # 2) Retirer le membre
        success = await MatchmakingService.remove_member_from_team(self.code, interaction.user.id)
        if success:
            # 3) Récupérer les membres restants
            members = await MatchmakingService.get_team_members(self.code)

            # 4) Transfert de lead si besoin
            if team["leader_id"] == interaction.user.id:
                if len(members) > 0:
                    new_leader_id = members[0]
                    await MatchmakingService.update_team_leader(self.code, new_leader_id)
                    logger.info(f"Transfert du lead de {interaction.user.id} vers {new_leader_id} pour l'équipe {self.code}.")
                else:
                    logger.info(f"Le leader quitte et l'équipe est vide => suppression imminente.")

            if len(members) == 0:
                logger.info(f"L'équipe '{self.code}' est vide => suppression.")

                # 1) Répondre à l'utilisateur
                await interaction.followup.send(
                    content="Vous avez quitté l'équipe. Elle est vide et va être supprimée.",
                    ephemeral=True
                )

                # 2) Supprimer les ressources Discord
                team_data = await MatchmakingService.get_team(self.code)
                if team_data:
                    await self.cog.delete_team_resources(team_data)

                    # 3) Supprimer dans la BDD
                    await MatchmakingService.delete_team(self.code)

            else:
                await self.cog.update_team_thread(self.code)
                await interaction.followup.send(
                    content="Vous avez quitté l'équipe.",
                    ephemeral=True
                )
        else:
            await interaction.followup.send(
                content="Erreur lors de la tentative de quitter l'équipe.",
                ephemeral=True
            )
