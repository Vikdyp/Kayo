# cogs/moderation/unban_requests.py
"""
Cog pour gérer les demandes de débannissement.
Aucun accès DB direct - délègue aux services.
"""

import discord
from discord.ext import commands
import logging
import asyncio
from datetime import datetime

from cogs.moderation.constants import MSG_TYPE_UNBAN_PANEL
from cogs.moderation.presenters import (
    build_deban_panel_embed,
    build_deban_request_channel_name,
    build_deban_request_embed,
)
from cogs.moderation.services.moderation_service import ModerationService
from cogs.moderation.views.unban_request_views import (
    DebanManagerView,
    DebanRequestActionView,
    DebanRequestModal,
)

logger = logging.getLogger(__name__)


class DebanManager(commands.Cog):
    """Cog pour gérer les demandes de débannissement de manière unique et persistante."""

    def __init__(
        self,
        bot: commands.Bot,
        moderation_service: ModerationService,
    ):
        self.bot = bot
        self._mod_svc = moderation_service
        self._reload_views_task: asyncio.Task | None = None
        logger.info("DebanManager Cog initialisé.")
        self._reload_views_task = asyncio.create_task(self.reload_persistent_views())

    def cog_unload(self):
        if self._reload_views_task:
            self._reload_views_task.cancel()

    @property
    def _unban_requests_svc(self):
        """Accès au service de demandes de déban via le bot."""
        return self.bot.unban_requests_svc

    @commands.command(name="send_deban")
    @commands.has_permissions(administrator=True)
    async def send_deban(self, ctx: commands.Context):
        """
        Commande pour envoyer l'embed principal de demande de débannissement.
        Usage: !send_deban
        """
        guild = ctx.guild
        if not guild:
            await ctx.send("Cette commande doit être utilisée dans un serveur.", delete_after=10)
            return

        # Vérifier s'il existe déjà une embed principale
        try:
            existing = await self._mod_svc.get_persistent_message(
                guild.id, MSG_TYPE_UNBAN_PANEL
            )
            if existing:
                await ctx.send(
                    "Une embed de demande de débannissement est déjà configurée. "
                    "Vous ne pouvez en créer qu'une seule.",
                    delete_after=15
                )
                return
        except Exception as e:
            logger.error(f"Erreur lors de la vérification des embeds existants: {e}")
            await ctx.send("Erreur interne. Veuillez contacter un administrateur.", delete_after=10)
            return

        # Récupérer le salon de demande-deban
        try:
            deban_channel_id = await self._mod_svc.get_deban_channel_id(guild.id)
            if not deban_channel_id:
                await ctx.send(
                    "Aucun salon de demande-deban configuré. "
                    "Veuillez contacter un administrateur.",
                    delete_after=10
                )
                return
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du salon: {e}")
            await ctx.send("Erreur interne. Veuillez contacter un administrateur.", delete_after=10)
            return

        deban_channel = guild.get_channel(deban_channel_id)
        if not deban_channel:
            await ctx.send("Salon de demande-deban introuvable. Veuillez contacter un administrateur.", delete_after=10)
            return

        embed = build_deban_panel_embed(timestamp=datetime.utcnow())

        view = DebanManagerView(self)

        # Envoyer l'embed
        try:
            message = await deban_channel.send(embed=embed, view=view)
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi de l'embed principal: {e}")
            await ctx.send("Erreur lors de l'envoi de la demande. Veuillez réessayer plus tard.", delete_after=10)
            return

        # Enregistrer l'embed principal
        try:
            await self._mod_svc.save_persistent_message(
                guild_id=guild.id,
                guild_name=guild.name,
                message_type=MSG_TYPE_UNBAN_PANEL,
                channel_id=deban_channel_id,
                message_id=message.id,
            )
            logger.info(f"Embed principal de demande de débannissement envoyé et persisté avec ID {message.id}")
        except Exception as e:
            logger.error(f"Erreur lors de l'enregistrement de l'embed principal: {e}")
            await ctx.send("Erreur lors de l'enregistrement de la demande. Veuillez réessayer plus tard.", delete_after=10)
            return

        await ctx.send(f"Embed principal de demande de débannissement envoyé dans {deban_channel.mention}.", delete_after=10)

    @send_deban.error
    async def send_deban_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("Vous n'avez pas les permissions nécessaires pour utiliser cette commande.", delete_after=10)
        else:
            logger.error(f"Erreur dans la commande send_deban: {error}")
            await ctx.send("Une erreur est survenue. Veuillez réessayer plus tard.", delete_after=10)

    async def open_deban_request_modal(self, interaction: discord.Interaction):
        """Ouvre le modal pour la demande de débannissement."""
        modal = DebanRequestModal(self, interaction.user)
        await interaction.response.send_modal(modal)

    async def handle_deban_request_submission(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        reason: str
    ):
        """Gère la soumission du formulaire de demande de débannissement."""
        guild = interaction.guild
        if not guild:
            logger.error("Interaction sans guild.")
            await interaction.followup.send("Erreur interne. Veuillez contacter un administrateur.", ephemeral=True)
            return

        # Vérifier si l'utilisateur a déjà une demande en cours
        try:
            has_pending = await self._unban_requests_svc.has_pending_request(guild.id, user.id)
            if has_pending:
                await interaction.followup.send(
                    "Vous avez déjà une demande de débannissement en cours. "
                    "Veuillez attendre qu'elle soit traitée avant d'en soumettre une nouvelle.",
                    ephemeral=True
                )
                return
        except Exception as e:
            logger.error(f"Erreur lors de la vérification des demandes en cours: {e}")
            await interaction.followup.send("Erreur interne. Veuillez contacter un administrateur.", ephemeral=True)
            return

        # Vérifier si l'utilisateur est banni
        ban_info = await self._mod_svc.get_ban_info(guild.id, user.id)
        if not ban_info:
            await interaction.followup.send("Vous n'êtes actuellement pas banni.", ephemeral=True)
            return

        # Récupérer la catégorie de déban
        category_id = await self._mod_svc.get_deban_category_id(guild.id)
        if not category_id:
            await interaction.followup.send(
                "La catégorie de déban n'est pas configurée. Veuillez contacter un administrateur.",
                ephemeral=True
            )
            return

        # Récupérer le rôle admin
        admin_role_id = await self._mod_svc.get_role_id_by_name(guild.id, "admin")
        if not admin_role_id:
            await interaction.followup.send(
                "Le rôle admin n'est pas configuré. Veuillez contacter un administrateur.",
                ephemeral=True
            )
            return

        channel_name = build_deban_request_channel_name(user.name)

        try:
            category = guild.get_channel(category_id)
            if not category or not isinstance(category, discord.CategoryChannel):
                await interaction.followup.send(
                    "Catégorie spécifiée introuvable. Veuillez contacter un administrateur.",
                    ephemeral=True
                )
                return

            admin_role = guild.get_role(admin_role_id)
            if not admin_role:
                await interaction.followup.send(
                    "Le rôle admin est introuvable. Veuillez contacter un administrateur.",
                    ephemeral=True
                )
                return

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                admin_role: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }

            request_channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                reason=f"Demande de débannissement de {user}"
            )
            logger.info(f"Salon '{channel_name}' créé pour la demande de débannissement de {user}.")

        except Exception as e:
            logger.error(f"Erreur lors de la création du salon: {e}")
            await interaction.followup.send(
                "Erreur lors de la création du salon de demande de débannissement. Veuillez réessayer plus tard.",
                ephemeral=True
            )
            return

        banned_by_mention = "Utilisateur inconnu"
        if ban_info.moderator_discord_id:
            banned_by_user = guild.get_member(ban_info.moderator_discord_id)
            if banned_by_user:
                banned_by_mention = banned_by_user.mention

        embed = build_deban_request_embed(
            user_mention=user.mention,
            user_id=user.id,
            reason=reason,
            ban_info=ban_info,
            banned_by_mention=banned_by_mention,
            requester_label=str(interaction.user),
            requester_avatar_url=interaction.user.avatar.url if interaction.user.avatar else None,
            timestamp=datetime.utcnow(),
        )

        # Envoyer l'embed (on a besoin du message_id pour créer la demande)
        try:
            # Créer une vue temporaire sans request_id
            temp_view = discord.ui.View(timeout=None)
            message = await request_channel.send(embed=embed, view=temp_view)
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi de la demande individuelle: {e}")
            await interaction.followup.send(
                "Erreur lors de l'envoi de la demande. Veuillez réessayer plus tard.",
                ephemeral=True
            )
            try:
                await request_channel.delete(reason="Erreur lors de l'envoi de la demande.")
            except Exception as delete_error:
                logger.error(f"Erreur lors de la suppression du salon: {delete_error}")
            return

        # Enregistrer la demande dans la base de données
        try:
            request_info = await self._unban_requests_svc.create_request(
                guild_id=guild.id,
                guild_name=guild.name,
                requester_discord_id=user.id,
                channel_id=request_channel.id,
                message_id=message.id,
                reason=reason,
            )
            logger.info(f"Demande de débannissement créée avec ID {request_info.id}")
        except Exception as e:
            logger.error(f"Erreur lors de l'enregistrement de la demande: {e}")
            await interaction.followup.send(
                "Erreur lors de l'enregistrement de la demande. Veuillez réessayer plus tard.",
                ephemeral=True
            )
            try:
                await request_channel.delete(reason="Erreur lors de l'enregistrement de la demande.")
            except Exception as delete_error:
                logger.error(f"Erreur lors de la suppression du salon: {delete_error}")
            return

        # Mettre à jour le message avec la vraie vue
        view = DebanRequestActionView(
            self,
            user_id=user.id,
            request_id=request_info.id,
            channel_id=request_channel.id
        )
        try:
            await message.edit(view=view)
            self.bot.add_view(view, message_id=message.id)
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour de la vue: {e}")

        await interaction.followup.send("Votre demande de débannissement a été envoyée.", ephemeral=True)

    async def process_accept(
        self,
        interaction: discord.Interaction,
        user_id: int,
        request_id: int
    ):
        """Processus d'acceptation de la demande de débannissement."""
        await interaction.response.defer(ephemeral=True)

        if not interaction.user.guild_permissions.ban_members:
            await interaction.followup.send(
                "Vous n'avez pas les permissions nécessaires pour effectuer cette action.",
                ephemeral=True
            )
            return

        guild = interaction.guild
        if not guild:
            await interaction.followup.send("Erreur interne. Veuillez contacter un administrateur.", ephemeral=True)
            return

        # Obtenir le cog Moderation pour le unban
        moderation_cog = self.bot.get_cog("Moderation")
        if not moderation_cog:
            logger.error("Cog de Modération non trouvé.")
            await interaction.followup.send("Erreur interne. Veuillez contacter un administrateur.", ephemeral=True)
            return

        # Appeler la méthode unban_member
        try:
            await moderation_cog.unban_member(guild, user_id, reason="Débannissement via demande de débannissement.")
            logger.info(f"Demande de débannissement acceptée pour l'utilisateur ID {user_id} par {interaction.user}.")
        except Exception as e:
            logger.error(f"Erreur lors de l'appel à unban_member: {e}")
            await interaction.followup.send("Erreur lors du débannissement. Veuillez réessayer.", ephemeral=True)
            return

        # Marquer la demande comme acceptée
        try:
            await self._unban_requests_svc.accept(request_id, interaction.user.id)
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour de la demande: {e}")

        await interaction.followup.send(
            "La demande de débannissement a été acceptée et l'utilisateur a été débanni.",
            ephemeral=True
        )

        # Supprimer le salon de la demande
        try:
            await interaction.channel.delete(reason=f"Demande de débannissement acceptée par {interaction.user}")
            logger.info("Salon de demande de débannissement supprimé après acceptation.")
        except Exception as e:
            logger.error(f"Erreur lors de la suppression du salon: {e}")

    async def process_reject(
        self,
        interaction: discord.Interaction,
        user_id: int,
        request_id: int
    ):
        """Processus de refus de la demande de débannissement."""
        await interaction.response.defer(ephemeral=True, thinking=True)

        if not interaction.user.guild_permissions.ban_members:
            await interaction.followup.send(
                "Vous n'avez pas les permissions nécessaires pour effectuer cette action.",
                ephemeral=True
            )
            return

        guild = interaction.guild
        if not guild:
            await interaction.followup.send("Erreur interne. Veuillez contacter un administrateur.", ephemeral=True)
            return

        # Informer l'utilisateur via DM
        try:
            user_dm = await self.bot.fetch_user(user_id)
            await user_dm.send(f"Votre demande de débannissement a été refusée sur le serveur **{guild.name}**.")
            logger.info(f"DM envoyé à l'utilisateur ID {user_id} pour le refus de la demande.")
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi du DM: {e}")

        # Marquer la demande comme rejetée
        try:
            await self._unban_requests_svc.reject(request_id, interaction.user.id)
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour de la demande: {e}")

        await interaction.followup.send("La demande de débannissement a été refusée.", ephemeral=True)

        # Supprimer le salon de la demande
        try:
            await interaction.channel.delete(reason=f"Demande de débannissement refusée par {interaction.user}")
            logger.info("Salon de demande de débannissement supprimé après refus.")
        except Exception as e:
            logger.error(f"Erreur lors de la suppression du salon: {e}")

    async def reload_persistent_views(self):
        """
        Recharge les vues persistantes pour les messages enregistrés.
        Cette méthode est appelée au démarrage du bot pour restaurer les interactions.
        """
        await self.bot.wait_until_ready()
        logger.info("Rechargement des vues persistantes pour les demandes de débannissement...")

        for guild in self.bot.guilds:
            # Récupérer l'embed principal de demande de débannissement
            message_data = await self._mod_svc.get_persistent_message(
                guild.id, MSG_TYPE_UNBAN_PANEL
            )
            if message_data:
                channel = guild.get_channel(message_data["channel_id"])
                if not channel:
                    logger.warning(f"Canal introuvable : {message_data['channel_id']} dans guild_id={guild.id}")
                else:
                    try:
                        message = await channel.fetch_message(message_data["message_id"])
                        view = DebanManagerView(self)
                        self.bot.add_view(view, message_id=message.id)
                        logger.info(f"Vue ajoutée pour l'embed principal ID {message.id}")
                    except discord.NotFound:
                        logger.warning(f"Message principal introuvable : {message_data['message_id']}")
                    except Exception as e:
                        logger.error(f"Erreur lors du rechargement de la vue principale: {e}")

            # Récupérer toutes les demandes individuelles
            try:
                pending_requests = await self._unban_requests_svc.list_pending(guild.id)
                for request in pending_requests:
                    channel = guild.get_channel(request.channel_id)
                    if not channel:
                        logger.warning(f"Canal introuvable : {request.channel_id}")
                        continue
                    try:
                        message = await channel.fetch_message(request.message_id)
                        view = DebanRequestActionView(
                            self,
                            user_id=request.requester_discord_id,
                            request_id=request.id,
                            channel_id=request.channel_id
                        )
                        self.bot.add_view(view, message_id=message.id)
                        logger.info(f"Vue ajoutée pour la demande individuelle ID {message.id}")
                    except discord.NotFound:
                        logger.warning(f"Message individuel introuvable : {request.message_id}")
                    except Exception as e:
                        logger.error(f"Erreur lors du rechargement de la vue individuelle: {e}")
            except Exception as e:
                logger.error(f"Erreur lors de la récupération des demandes en cours: {e}")


async def setup(bot: commands.Bot):
    moderation_service = getattr(bot, "moderation_service", None)
    if moderation_service is None:
        logger.error("moderation_service non initialisé. DebanManager ne sera pas chargé.")
        return

    unban_requests_service = getattr(bot, "unban_requests_svc", None)
    if unban_requests_service is None:
        logger.error("unban_requests_svc non initialisé. DebanManager ne sera pas chargé.")
        return

    await bot.add_cog(DebanManager(bot, moderation_service))
    logger.info("DebanManager Cog chargé avec succès.")
