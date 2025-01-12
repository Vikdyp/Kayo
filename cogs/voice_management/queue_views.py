import logging
import random
import string
from typing import List, Optional

import discord
from discord import ButtonStyle, Interaction
from discord.ui import Button, Select, View

from cogs.voice_management.services.five_stack_service import MatchmakingService

# On définit le logger local du module :
logger = logging.getLogger(__name__)


# -------------------------
# Vues de Confirmation MMR
# -------------------------

class MMRConfirmationView(View):
    """
    Vue de confirmation pour le MMR étendu.
    Pour un 'solo' ou 'team' qui veut s'inscrire avec mmr_extended=True/False.
    """
    def __init__(
        self,
        cog,
        guild_id: int,
        user: discord.Member,
        team_size: int,
        langue: str,
        region: str,
        platform: str,
        elo: int,
        roles: List[str],
        entry_type: str  # 'solo' ou 'team'
    ):
        super().__init__(timeout=60)
        self.cog = cog
        self.guild_id = guild_id
        self.user = user
        self.team_size = team_size
        self.langue = langue
        self.region = region
        self.platform = platform
        self.elo = elo
        self.roles = roles
        self.entry_type = entry_type

    @discord.ui.button(label="Oui", style=ButtonStyle.success, custom_id="mmr_confirm_yes")
    async def confirm_yes(self, interaction: Interaction, button: Button):
        """
        L'utilisateur accepte le mmr_extended=True.
        """
        try:
            if self.entry_type == "solo":
                # On appelle la méthode du cog pour un solo
                await self.cog.add_solo_to_queue(
                    user=self.user,
                    langue=self.langue,
                    region=self.region,
                    platform=self.platform,
                    team_size=self.team_size,
                    mmr_extended=True,
                    elo=self.elo,
                    roles=self.roles
                )
            else:
                # Cas 'team' : on suppose qu'on a déjà récupéré l'info qu'ils sont tous ensemble
                # Mais ici, on n'a qu'un "leader" => On va faire un appel dédié
                await self.cog.add_preformed_team_to_queue(
                    leader=self.user,
                    desired_size=self.team_size,
                    mmr_extended=True,
                    langue=self.langue,
                    region=self.region,
                    platform=self.platform,
                    roles=self.roles
                )

            await interaction.response.send_message(
                f"Votre équipe (ou vous en solo) avez rejoint la queue en mmr_extended=True.",
                ephemeral=True
            )
            logger.info(
                f"[MMRView] {self.user.display_name} => mmr_extended=True, "
                f"team_size={self.team_size}, entry_type={self.entry_type}"
            )
        except Exception as e:
            logger.error(f"Erreur MMRConfirmYes: {e}")
            await interaction.response.send_message(
                "Erreur lors de l'inscription MMR extended.", ephemeral=True
            )
        finally:
            self.stop()

    @discord.ui.button(label="Non", style=ButtonStyle.danger, custom_id="mmr_confirm_no")
    async def confirm_no(self, interaction: Interaction, button: Button):
        """
        L'utilisateur refuse le mmr_extended => False.
        """
        try:
            if self.entry_type == "solo":
                await self.cog.add_solo_to_queue(
                    user=self.user,
                    langue=self.langue,
                    region=self.region,
                    platform=self.platform,
                    team_size=self.team_size,
                    mmr_extended=False,
                    elo=self.elo,
                    roles=self.roles
                )
            else:
                await self.cog.add_preformed_team_to_queue(
                    leader=self.user,
                    desired_size=self.team_size,
                    mmr_extended=False,
                    langue=self.langue,
                    region=self.region,
                    platform=self.platform,
                    roles=self.roles
                )

            await interaction.response.send_message(
                "Inscription en queue sans extension de MMR.",
                ephemeral=True
            )
            logger.info(
                f"[MMRView] {self.user.display_name} => mmr_extended=False, "
                f"team_size={self.team_size}, entry_type={self.entry_type}"
            )
        except Exception as e:
            logger.error(f"Erreur MMRConfirmNo: {e}")
            await interaction.response.send_message(
                "Erreur lors de l'inscription en queue (mmr_extended=False).", 
                ephemeral=True
            )
        finally:
            self.stop()


# -------------------------
# Sélecteur de Taille d'Équipe
# -------------------------

class TeamSizeSelect(Select):
    """
    Menu déroulant pour choisir 2,3,5 ou 0 ('N'importe').
    entry_type = 'solo' ou 'team'.
    """
    def __init__(self, cog, guild_id: int, entry_type: str):
        options = [
            discord.SelectOption(label="Duo", description="Jouer en duo (2 joueurs)", value="2"),
            discord.SelectOption(label="Trio", description="Jouer en trio (3 joueurs)", value="3"),
            discord.SelectOption(label="5 Stack", description="Jouer en 5 Stack (5 joueurs)", value="5"),
            discord.SelectOption(label="N'importe", description="Aucune préférence de taille", value="0"),
        ]
        super().__init__(
            placeholder="Sélectionnez la taille de l'équipe...", 
            min_values=1, 
            max_values=1, 
            options=options
        )
        self.cog = cog
        self.guild_id = guild_id
        self.entry_type = entry_type

    async def callback(self, interaction: Interaction):
        user = interaction.user
        selected_value = self.values[0]
        team_size = int(selected_value)

        try:
            in_queue = await MatchmakingService.is_player_in_queue(user.id)
            if in_queue:
                await interaction.response.send_message(
                    "Vous êtes déjà dans la queue.", ephemeral=True
                )
                return

            user_info = await MatchmakingService.get_user_info(user.id)
            elo = user_info.get("elo", 1500) if user_info else 1500
            region = user_info.get("region", "EU") if user_info else "EU"

            server_id = await MatchmakingService.get_server_id_by_guild_id(self.guild_id)
            if not server_id:
                await interaction.response.send_message(
                    "Impossible de récupérer server_id.", ephemeral=True
                )
                return

            user_roles = await MatchmakingService.get_user_roles_from_member(user, server_id)
            langue = next((r for r in ["francais", "anglais", "espagnol"] if r in user_roles), "francais")
            platform = next((r for r in ["pc", "console"] if r in user_roles), "pc")
            roles = [r for r in ["duelist","controller","initiator","sentinel","fill"] if r in user_roles]
            if not roles:
                roles = ["duelist"]

            if self.entry_type == "team":
                code = await MatchmakingService.is_user_leader_of_team(user.id)
                if not code:
                    await interaction.response.send_message(
                        "Vous n'êtes pas leader d'une équipe. Seul le leader peut inscrire l'équipe en queue.",
                        ephemeral=True
                    )
                    return

            # MMR confirmation pour 5 ou 0
            if team_size in [5, 0]:
                mmr_view = MMRConfirmationView(
                    cog=self.cog,
                    guild_id=self.guild_id,
                    user=user,
                    team_size=team_size,
                    langue=langue,
                    region=region,
                    platform=platform,
                    elo=elo,
                    roles=roles,
                    entry_type=self.entry_type
                )
                await interaction.response.send_message(
                    "Acceptez-vous l'extension MMR (jusqu'à 300 de différence) ?",
                    view=mmr_view,
                    ephemeral=True
                )
            else:
                # Pas de MMR confirmation => inscription directe
                if self.entry_type == "solo":
                    await self.cog.add_solo_to_queue(
                        user=user,
                        langue=langue,
                        region=region,
                        platform=platform,
                        team_size=team_size,
                        mmr_extended=False,
                        elo=elo,
                        roles=roles
                    )
                    await interaction.response.send_message(
                        f"Vous avez rejoint la queue en solo (team_size={team_size}).",
                        ephemeral=True
                    )
                else:
                    # entry_type=team
                    await self.cog.add_preformed_team_to_queue(
                        leader=user,
                        desired_size=team_size,
                        mmr_extended=False,
                        langue=langue,
                        region=region,
                        platform=platform,
                        roles=roles
                    )
                    await interaction.response.send_message(
                        f"Votre équipe est inscrite dans la queue (team_size={team_size}, mmr_extended=False).",
                        ephemeral=True
                    )

        except Exception as e:
            logger.error(f"[TeamSizeSelect callback] Erreur: {e}")
            await interaction.response.send_message(
                f"Erreur lors de la sélection de la taille d'équipe: {e}",
                ephemeral=True
            )

# -------------------------
# Vue Principale de la Queue
# -------------------------

class QueueView(View):
    """
    Vue avec 3 boutons:
     - Rejoindre en solo
     - Rejoindre en équipe
     - Quitter la queue
    """
    def __init__(self, cog, guild_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id

    @discord.ui.button(
        label="Rejoindre en solo",
        style=ButtonStyle.primary,
        custom_id="join_solo_button",
    )
    async def join_solo_button(self, interaction: Interaction, button: Button):
        try:
            select = TeamSizeSelect(self.cog, self.guild_id, entry_type="solo")
            v = View(timeout=60)
            v.add_item(select)
            await interaction.response.send_message(
                "Sélectionnez la taille de votre équipe (2 ou 3 pour éviter la confirmation MMR, 5 ou 0 = MMR confirmation) :", 
                view=v, 
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Erreur join_solo_button: {e}")
            await interaction.response.send_message(
                "Une erreur est survenue lors de l'affichage du menu.", ephemeral=True
            )

    @discord.ui.button(
        label="Rejoindre en équipe",
        style=ButtonStyle.success,
        custom_id="join_team_button",
    )
    async def join_team_button(self, interaction: Interaction, button: Button):
        """
        Bouton pour insérer "une équipe préformée" dans la queue, 
        à condition que l'utilisateur soit le leader.
        """
        try:
            select = TeamSizeSelect(self.cog, self.guild_id, entry_type="team")
            v = View(timeout=60)
            v.add_item(select)
            await interaction.response.send_message(
                "Sélectionnez la taille finale souhaitée (2,3,5,0) pour votre équipe préformée :", 
                view=v, 
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Erreur join_team_button: {e}")
            await interaction.response.send_message(
                "Une erreur est survenue lors de l'affichage du menu d'équipe.", 
                ephemeral=True
            )

    @discord.ui.button(
        label="Quitter la queue",
        style=ButtonStyle.danger,
        custom_id="leave_queue_button",
    )
    async def leave_queue_button(self, interaction: Interaction, button: Button):
        """
        Permet au joueur/leader de sortir de la queue s'il y est.
        """
        user = interaction.user
        try:
            await self.cog.remove_from_queue(user)
            await interaction.response.send_message(
                "Vous avez quitté la queue.", ephemeral=True
            )
            logger.info(f"{user.display_name} a quitté la queue.")
        except ValueError as ve:
            logger.error(f"Erreur leave_queue_button: {ve}")
            await interaction.response.send_message(str(ve), ephemeral=True)
        except Exception as e:
            logger.error(f"Erreur retrait queue: {e}")
            await interaction.response.send_message(
                "Une erreur est survenue lors de votre demande de quitter la queue.",
                ephemeral=True,
            )
