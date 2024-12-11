import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button
from datetime import datetime
import logging

from cogs.utilities.data_manager import DataManager
from cogs.utilities.request_manager import enqueue_request

logger = logging.getLogger("discord.unban_requests")


class UnbanRequestView(View):
    """Vue contenant les boutons pour accepter ou refuser une demande de débannissement."""

    def __init__(self, bot: commands.Bot, user_id: int, requester: discord.User):
        super().__init__(timeout=300)  # Timeout après 5 minutes
        self.bot = bot
        self.user_id = user_id
        self.requester = requester

    @discord.ui.button(label="Accepter", style=discord.ButtonStyle.green, custom_id="unban_accept")
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handler pour le bouton Accepter."""
        try:
            if not interaction.user.guild_permissions.administrator:
                await interaction.followup.send(
                    "Vous n'avez pas les permissions nécessaires pour effectuer cette action.",
                    ephemeral=True,
                )
                return

            # Accéder au cog Moderation
            moderation_cog = self.bot.get_cog("Moderation")
            if not moderation_cog:
                logger.error("Cog 'Moderation' introuvable.")
                await interaction.followup.send(
                    "Impossible de débannir cet utilisateur car le cog de modération est introuvable.",
                    ephemeral=True,
                )
                return

            # Étape 1 : Débannir l'utilisateur
            logger.debug(f"Tentative de débannissement de l'utilisateur ID: {self.user_id} via le bouton.")
            await moderation_cog.unban_member(
                user_id=self.user_id,
                reason="Demande de débannissement acceptée"
            )
            logger.info(f"Utilisateur ID: {self.user_id} débanni avec succès.")

            # Étape 2 : Restaurer les rôles sauvegardés
            guild = interaction.guild
            if not guild:
                logger.error("Serveur introuvable lors de la tentative de restauration des rôles.")
                await interaction.followup.send(
                    "Une erreur est survenue lors de la restauration des rôles de l'utilisateur.",
                    ephemeral=True,
                )
                return

            member = guild.get_member(self.user_id)
            if member:
                logger.debug(f"Restauration des rôles pour l'utilisateur {member.display_name}.")
                await moderation_cog.restore_roles(member)
            else:
                logger.warning(f"L'utilisateur ID: {self.user_id} n'est pas présent dans le serveur pour la restauration des rôles.")

            # Étape 3 : Informer l'utilisateur via DM
            try:
                user = await self.bot.fetch_user(self.user_id)
                if user:
                    await user.send(
                        f"Vous avez été débanni du serveur **{guild.name}**.\n"
                        f"**Raison :** Demande de débannissement acceptée."
                    )
                    logger.info(f"DM envoyé à l'utilisateur {user.display_name} pour le débannissement.")
                else:
                    logger.warning(f"Impossible de trouver l'utilisateur ID: {self.user_id} pour l'envoi d'un DM.")
            except discord.Forbidden:
                logger.warning(f"Impossible d'envoyer un DM à l'utilisateur ID: {self.user_id}. Permissions manquantes.")
            except discord.HTTPException as e:
                logger.error(f"Erreur HTTP lors de l'envoi du DM à l'utilisateur ID: {self.user_id}: {e}")

            # Étape finale : Confirmer le succès
            await interaction.followup.send(
                "L'utilisateur a été débanni et ses rôles ont été restaurés avec succès.",
                ephemeral=True,
            )
        except Exception as e:
            logger.error(f"Erreur inattendue dans accept_button : {e}")
            await interaction.followup.send(
                "Une erreur inattendue est survenue lors du débannissement.",
                ephemeral=True,
            )
        finally:
            self.stop()



    @discord.ui.button(label="Refuser", style=discord.ButtonStyle.red, custom_id="unban_reject")
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handler pour le bouton Refuser."""
        try:
            if not interaction.user.guild_permissions.administrator:
                await interaction.followup.send(
                    "Vous n'avez pas les permissions nécessaires pour effectuer cette action.",
                    ephemeral=True,
                )
                return

            try:
                await interaction.message.delete()
                await interaction.followup.send(
                    "La demande de débannissement a été refusée et la demande a été supprimée.",
                    ephemeral=True,
                )
                logger.info(f"Unban refusé pour l'utilisateur ID: {self.user_id} par {interaction.user}")
            except discord.Forbidden:
                logger.error("Permission refusée pour supprimer le message de demande de débannissement.")
                await interaction.followup.send(
                    "Je n'ai pas les permissions nécessaires pour supprimer le message de demande de débannissement.",
                    ephemeral=True,
                )
        except Exception as e:
            logger.error(f"Erreur dans reject_button : {e}")
            await interaction.followup.send("Une erreur inattendue est survenue.", ephemeral=True)
        finally:
            self.stop()


class UnbanRequests(commands.Cog):
    """Cog pour gérer les demandes de débannissement."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = DataManager()
        logger.info("Initialisation du Cog UnbanRequests.")

    async def cog_unload(self):
        logger.info("Cog UnbanRequests déchargé.")

    @app_commands.command(name="demande_deban", description="Envoyer une demande de débannissement pour un utilisateur")
    @app_commands.describe(
        user="Utilisateur à débannir",
        raison="Raison de la demande de débannissement"
    )
    @app_commands.checks.has_permissions(administrator=True)
    @enqueue_request()  # Utilisation du décorateur pour gérer la file d'attente
    async def demande_deban(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        raison: str
    ):
        """Permet d'envoyer une demande de débannissement pour un utilisateur."""
        logger.debug(f"Commande 'demande_deban' appelée pour {user} par {interaction.user.display_name}. Raison: {raison}")

        # Chargement de la configuration
        config = await self.data.get_config()

        # Récupération de l'ID du salon "demande-deban"
        demande_deban_channel_id = config.get("channels", {}).get("demande-deban")
        if not demande_deban_channel_id:
            logger.error("ID du salon 'demande-deban' non trouvé ou invalide dans config.json.")
            await interaction.followup.send(
                "Le salon 'demande-deban' n'est pas configuré correctement.",
                ephemeral=True
            )
            return

        # Vérification que le salon existe
        demande_deban_channel = interaction.guild.get_channel(int(demande_deban_channel_id))
        if not demande_deban_channel:
            logger.error(f"Le salon 'demande-deban' avec l'ID {demande_deban_channel_id} est introuvable.")
            await interaction.followup.send(
                "Le salon 'demande-deban' est introuvable sur ce serveur.",
                ephemeral=True
            )
            return

        # Préparation de l'embed pour la demande
        embed = discord.Embed(
            title=f"Demande de débannissement pour {user.display_name}",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="Utilisateur", value=f"{user} (ID: {user.id})", inline=False)
        embed.add_field(name="Raison de la demande de débannissement", value=raison, inline=False)
        embed.set_footer(text="Demande de Débannissement")

        view = UnbanRequestView(self.bot, user.id, interaction.user)
        try:
            await demande_deban_channel.send(embed=embed, view=view)
            await interaction.followup.send(
                f"Demande de débannissement pour {user.display_name} envoyée dans {demande_deban_channel.mention}.",
                ephemeral=True
            )
            logger.info(f"{interaction.user} a envoyé une demande de débannissement pour {user.display_name}.")
        except discord.Forbidden:
            logger.error(f"Permission refusée pour envoyer un message dans {demande_deban_channel.name}.")
            await interaction.followup.send(
                "Je n'ai pas les permissions nécessaires pour envoyer des messages dans le salon 'demande-deban'.",
                ephemeral=True
            )
        except discord.HTTPException as e:
            logger.error(f"Erreur HTTP lors de l'envoi de la demande de débannissement: {e}")
            await interaction.followup.send(
                "Une erreur est survenue lors de l'envoi de la demande de débannissement.",
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(UnbanRequests(bot))
    logger.info("Cog UnbanRequests chargé avec succès.")
