#cogs\voice_management\queue_views.py

import logging
import time
from typing import Dict, List, Optional, Tuple

import discord
from discord import ButtonStyle, Interaction
from discord.ui import Button, Select, View

from cogs.five_stack.services.five_stack_service import MatchmakingService
from cogs.ranking.services.assign_rank_service import valorant_account_linked
from cogs.configuration.services.channel_service import ServerChannelService

# Constante pour l'ID du salon où l'utilisateur doit lier ses informations Valorant
VALORANT_INFO_ACTION = "rang"

# Rate limiting: cooldown en secondes et cache des dernières interactions
BUTTON_COOLDOWN_SECONDS = 3.0
_user_cooldowns: Dict[int, float] = {}  # {user_id: last_interaction_timestamp}

# Logger local
logger = logging.getLogger(__name__)


def check_rate_limit(user_id: int) -> Optional[float]:
    """
    Vérifie si un utilisateur est en cooldown.

    Args:
        user_id: ID Discord de l'utilisateur

    Returns:
        None si pas en cooldown, sinon le temps restant en secondes
    """
    now = time.time()
    last_use = _user_cooldowns.get(user_id, 0)
    elapsed = now - last_use

    if elapsed < BUTTON_COOLDOWN_SECONDS:
        return BUTTON_COOLDOWN_SECONDS - elapsed

    _user_cooldowns[user_id] = now
    return None


def cleanup_old_cooldowns() -> None:
    """Nettoie les entrées de cooldown obsolètes (> 1 minute)."""
    now = time.time()
    expired = [uid for uid, ts in _user_cooldowns.items() if now - ts > 60]
    for uid in expired:
        del _user_cooldowns[uid]


# -------------------------
# Vues de Confirmation MMR
# -------------------------

class MMRConfirmationView(View):
    """
    Vue de confirmation pour l'utilisation du MMR étendu.
    Permet de choisir si l'on souhaite appliquer le malus de 25% (mmr_extended=True)
    ou non pour un 'solo' ou une 'team'.
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
    async def confirm_yes(self, interaction: Interaction, button: Button) -> None:
        """
        L'utilisateur accepte d'utiliser le MMR étendu (avec malus de 25%).
        """
        try:
            if self.entry_type == "solo":
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
                "Vous avez rejoint la queue.",
                ephemeral=True
            )
            logger.info(
                f"[MMRConfirmationView] {self.user.display_name} a choisi mmr_extended=True, "
                f"team_size={self.team_size}, entry_type={self.entry_type}"
            )
        except Exception as e:
            logger.error(f"Erreur dans confirm_yes: {e}")
            await interaction.response.send_message(
                "Erreur lors de l'inscription avec MMR étendu.",
                ephemeral=True
            )
        finally:
            self.stop()

    @discord.ui.button(label="Non", style=ButtonStyle.danger, custom_id="mmr_confirm_no")
    async def confirm_no(self, interaction: Interaction, button: Button) -> None:
        """
        L'utilisateur refuse d'utiliser le MMR étendu (mmr_extended=False).
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
                "Vous avez rejoint la queue.",
                ephemeral=True
            )
            logger.info(
                f"[MMRConfirmationView] {self.user.display_name} a choisi mmr_extended=False, "
                f"team_size={self.team_size}, entry_type={self.entry_type}"
            )
        except Exception as e:
            logger.error(f"Erreur dans confirm_no: {e}")
            await interaction.response.send_message(
                "Erreur lors de l'inscription sans MMR étendu.",
                ephemeral=True
            )
        finally:
            self.stop()


# -------------------------
# Sélecteur de Taille d'Équipe
# -------------------------

class TeamSizeSelect(Select):
    """
    Menu déroulant pour choisir la taille d'équipe (Duo, Trio, 5 Stack ou 'N'importe').
    Le paramètre entry_type détermine s'il s'agit d'une inscription en solo ou en équipe.
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

    async def callback(self, interaction: Interaction) -> None:
        try:
            # Extension de la fenêtre de réponse
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)

            user = interaction.user
            channel_ref = "`#rang`"
            if interaction.guild:
                channel_id = await ServerChannelService.get_channel_id(
                    interaction.guild.id,
                    interaction.guild.name,
                    VALORANT_INFO_ACTION,
                )
                if channel_id:
                    channel_ref = f"<#{channel_id}>"
            selected_value = self.values[0]
            team_size = int(selected_value)

            server_id = await MatchmakingService.get_server_id_by_guild_id(self.guild_id)
            if not server_id:
                await interaction.followup.send(
                    "Impossible de recuperer les informations du serveur. Reessayez plus tard.",
                    ephemeral=True
                )
                return

            # Vérifier si l'utilisateur est déjà en queue
            if await MatchmakingService.is_player_in_queue(server_id, user.id):
                await interaction.followup.send(
                    "Vous êtes déjà dans la queue.",
                    ephemeral=True
                )
                return

            # Vérification de la présence des infos Valorant
            if not await valorant_account_linked(user.id):
                await interaction.followup.send(
                    f"Veuillez lier votre compte dans le salon {channel_ref} avant de rejoindre la queue.",
                    ephemeral=True
                )
                return

            user_info = await MatchmakingService.get_user_info(user.id)

            elo = user_info.get("elo")
            region = user_info.get("region")
            if elo is None or region is None:
                await interaction.followup.send(
                    f"Vos informations Valorant sont incomplètes. "
                    f"Veuillez lier votre compte dans le salon {channel_ref} avant de rejoindre la queue.",
                    ephemeral=True
                )
                return

            # Récupération du server_id et des rôles de l'utilisateur
            server_id = await MatchmakingService.get_server_id_by_guild_id(self.guild_id)
            if not server_id:
                await interaction.followup.send(
                    "Impossible de récupérer les informations du serveur. Réessayez plus tard.",
                    ephemeral=True
                )
                return

            user_roles = await MatchmakingService.get_user_roles_from_member(user, server_id)
            # Extraction de la langue, de la plateforme et des rôles de jeu depuis les rôles Discord
            langue = next((r for r in ["francais", "anglais", "espagnol"] if r in user_roles), "francais")
            platform = next((r for r in ["pc", "console"] if r in user_roles), "pc")
            roles = [r for r in ["duelist", "controller", "initiator", "sentinel", "fill"] if r in user_roles]
            if not roles:
                roles = ["duelist"]

            # Vérification pour les équipes : seul le leader peut inscrire l'équipe
            if self.entry_type == "team":
                code = await MatchmakingService.is_user_leader_of_team(user.id, server_id)
                if not code:
                    await interaction.followup.send(
                        "Vous n'êtes pas leader d'une équipe. Seul le leader peut inscrire l'équipe dans la queue. "
                        "Utilisez /create_team pour créer votre équipe.",
                        ephemeral=True
                    )
                    return

            # Gestion de la confirmation MMR pour certaines tailles (5 ou 'N'importe')
            if team_size in [5, 0]:
                from .queue_views import MMRConfirmationView
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
                # Message clarifié pour indiquer le malus appliqué
                await interaction.followup.send(
                    "Accepter vous le -25% ?",
                    view=mmr_view,
                    ephemeral=True
                )
            else:
                # Inscription directe sans confirmation MMR étendu
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
                    await interaction.followup.send("Vous avez rejoint la queue.", ephemeral=True)
                else:
                    await self.cog.add_preformed_team_to_queue(
                        leader=user,
                        desired_size=team_size,
                        mmr_extended=False,
                        langue=langue,
                        region=region,
                        platform=platform,
                        roles=roles
                    )
                    await interaction.followup.send("Votre équipe est inscrite dans la queue.", ephemeral=True)

        except Exception as e:
            logger.error(f"[TeamSizeSelect callback] Erreur: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"Erreur lors de la sélection de la taille d'équipe: {e}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"Erreur lors de la sélection de la taille d'équipe: {e}",
                    ephemeral=True
                )


# -------------------------
# Vue Principale de la Queue
# -------------------------

class QueueView(View):
    """
    Vue principale comportant trois boutons :
     - Rejoindre en solo
     - Rejoindre en équipe
     - Quitter la queue
    """
    def __init__(self, cog, guild_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id

    def _create_team_size_view(self, entry_type: str) -> View:
        """
        Fonction helper pour créer et retourner un View contenant le sélecteur
        de taille d'équipe.
        """
        select = TeamSizeSelect(self.cog, self.guild_id, entry_type=entry_type)
        v = View(timeout=60)
        v.add_item(select)
        return v

    @discord.ui.button(
        label="Rejoindre en solo",
        style=ButtonStyle.primary,
        custom_id="join_solo_button",
    )
    async def join_solo_button(self, interaction: Interaction, button: Button) -> None:
        """
        Affiche le sélecteur pour rejoindre la queue en solo.
        """
        # Rate limiting
        remaining = check_rate_limit(interaction.user.id)
        if remaining is not None:
            await interaction.response.send_message(
                f"Veuillez patienter {remaining:.1f}s avant de réessayer.",
                ephemeral=True
            )
            return

        try:
            view = self._create_team_size_view(entry_type="solo")
            await interaction.response.send_message(
                "Sélectionnez la taille d'équipe (Duo, Trio, etc.) :",
                view=view,
                ephemeral=True
            )
        except discord.HTTPException as e:
            logger.error(f"Erreur HTTP join_solo_button: {e}")
            await interaction.response.send_message(
                "Une erreur est survenue lors de l'affichage du menu.",
                ephemeral=True
            )

    @discord.ui.button(
        label="Rejoindre en équipe",
        style=ButtonStyle.success,
        custom_id="join_team_button",
    )
    async def join_team_button(self, interaction: Interaction, button: Button) -> None:
        """
        Affiche le sélecteur pour inscrire une équipe préformée dans la queue.
        Seul le leader peut inscrire l'équipe.
        """
        # Rate limiting
        remaining = check_rate_limit(interaction.user.id)
        if remaining is not None:
            await interaction.response.send_message(
                f"Veuillez patienter {remaining:.1f}s avant de réessayer.",
                ephemeral=True
            )
            return

        try:
            view = self._create_team_size_view(entry_type="team")
            await interaction.response.send_message(
                "Sélectionnez la taille d'équipe (Duo, Trio, etc.) :",
                view=view,
                ephemeral=True
            )
        except discord.HTTPException as e:
            logger.error(f"Erreur HTTP join_team_button: {e}")
            await interaction.response.send_message(
                "Une erreur est survenue lors de l'affichage du menu d'équipe.",
                ephemeral=True
            )

    @discord.ui.button(
        label="Quitter la queue",
        style=ButtonStyle.danger,
        custom_id="leave_queue_button",
    )
    async def leave_queue_button(self, interaction: Interaction, button: Button) -> None:
        """
        Permet au joueur ou leader de quitter la queue.
        """
        # Rate limiting
        remaining = check_rate_limit(interaction.user.id)
        if remaining is not None:
            await interaction.response.send_message(
                f"Veuillez patienter {remaining:.1f}s avant de réessayer.",
                ephemeral=True
            )
            return

        user = interaction.user
        try:
            await interaction.response.defer(ephemeral=True)
            await self.cog.remove_from_queue(user)
            await interaction.followup.send(
                "Vous avez quitté la queue.",
                ephemeral=True
            )
            logger.info(f"{user.display_name} a quitté la queue.")
        except ValueError as ve:
            logger.error(f"Erreur leave_queue_button: {ve}")
            await interaction.followup.send(str(ve), ephemeral=True)
        except discord.HTTPException as e:
            logger.error(f"Erreur HTTP lors du retrait de la queue: {e}")
            await interaction.followup.send(
                "Une erreur est survenue lors de votre demande de quitter la queue.",
                ephemeral=True,
            )
