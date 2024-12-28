# cogs/moderation/unban_requests.py

import discord
from discord.ext import commands, tasks
from discord.ui import View, Button, Modal, TextInput
import logging
from typing import Optional, Dict, List
from datetime import datetime

from cogs.moderation.services.moderation_service import ModerationService
from utils.database import database
from utils.request_manager import enqueue_button_request

logger = logging.getLogger("deban_manager")

# Vue pour l'embed principal de demande de débannissement
class DebanManagerView(View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Demander un Déban", style=discord.ButtonStyle.primary, custom_id="deban_manager:open_form")
    @enqueue_button_request("URGENT")
    async def open_form_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.open_deban_request_modal(interaction)

# Modal pour le formulaire de demande de débannissement
class DebanRequestModal(Modal):
    def __init__(self, cog, user: discord.User):
        super().__init__(title="Demande de Déban")
        self.cog = cog
        self.user = user

        self.add_item(TextInput(
            label="Raison de la demande",
            style=discord.TextStyle.long,
            placeholder="Expliquez pourquoi vous souhaitez être débanni.",
            required=True,
            max_length=1000
        ))

    async def on_submit(self, interaction: discord.Interaction):
        reason = self.children[0].value
        # Déférer l'interaction pour indiquer que vous allez répondre plus tard
        await interaction.response.defer(ephemeral=True)
        # Traiter la demande de débannissement
        await self.cog.handle_deban_request_submission(interaction, self.user, reason)
        # La confirmation est gérée dans handle_deban_request_submission

# Vue pour les actions des demandes individuelles
class DebanRequestActionView(View):
    def __init__(self, cog, user_id: int, requester_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.user_id = user_id
        self.requester_id = requester_id

    @discord.ui.button(label="Accepter", style=discord.ButtonStyle.success, custom_id="deban_request:accept")
    @enqueue_button_request("URGENT")
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.process_accept(interaction, self.user_id, self.requester_id)

    @discord.ui.button(label="Refuser", style=discord.ButtonStyle.danger, custom_id="deban_request:reject")
    @enqueue_button_request("URGENT")
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.process_reject(interaction, self.user_id, self.requester_id)

class DebanManager(commands.Cog):
    """Cog pour gérer les demandes de débannissement de manière unique et persistante."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("DebanManager Cog initialisé.")
        self.bot.loop.create_task(self.reload_persistent_views())

    @commands.command(name="send_deban")
    @commands.has_permissions(ban_members=True)
    async def send_deban(self, ctx: commands.Context):
        """
        Commande pour envoyer l'embed principal de demande de débannissement.
        Usage: !send_deban
        """
        guild = ctx.guild
        if not guild:
            await ctx.send("Cette commande doit être utilisée dans un serveur.", delete_after=10)
            return

        # Récupérer l'ID interne du serveur
        internal_server_id = await ModerationService.get_internal_server_id(guild.id)
        if not internal_server_id:
            await ctx.send("Erreur interne. Veuillez contacter un administrateur.", delete_after=10)
            return

        # Vérifier s'il existe déjà une embed principale de demande de débannissement
        try:
            existing_message_id = await ModerationService.get_persistent_message(internal_server_id, "demande_deban")
            if existing_message_id:
                await ctx.send("Une embed de demande de débannissement est déjà configurée. Vous ne pouvez en créer qu'une seule.", delete_after=15)
                return
        except Exception as e:
            logger.error(f"Erreur lors de la vérification des embeds existants: {e}")
            await ctx.send("Erreur interne. Veuillez contacter un administrateur.", delete_after=10)
            return

        # Créer l'embed principal
        embed = discord.Embed(
            title="🎫 Demande de Déban",
            description=(
                "Cliquez sur le bouton ci-dessous pour soumettre une demande de débannissement.\n"
                "Vous serez informé lors du traitement de votre demande."
            ),
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="Déban Manager")

        # Créer la vue avec le bouton
        view = DebanManagerView(self)

        # Récupérer le salon de modération
        try:
            moderation_channel_id = await ModerationService.get_deban_channel_id(internal_server_id)
            if not moderation_channel_id:
                await ctx.send("Aucun salon de modération configuré. Veuillez contacter un administrateur.", delete_after=10)
                return
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du salon de modération: {e}")
            await ctx.send("Erreur interne. Veuillez contacter un administrateur.", delete_after=10)
            return

        moderation_channel = guild.get_channel(moderation_channel_id)
        if not moderation_channel:
            await ctx.send("Salon de modération introuvable. Veuillez contacter un administrateur.", delete_after=10)
            return

        # Envoyer l'embed dans le salon de modération
        try:
            message = await moderation_channel.send(embed=embed, view=view)
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi de l'embed principal de demande de débannissement: {e}")
            await ctx.send("Erreur lors de l'envoi de la demande. Veuillez réessayer plus tard.", delete_after=10)
            return

        # Enregistrer l'embed principal dans la table `persistent_messages`
        insert_query = """
        INSERT INTO persistent_messages (channel_id, message_id, message_type, created_at, guild_id)
        VALUES ($1, $2, 'demande_deban', NOW(), $3)
        """
        try:
            await database.execute(insert_query, moderation_channel_id, message.id, internal_server_id)
            logger.info(f"Embed principal de demande de débannissement envoyé et persisté avec ID {message.id} dans le canal {moderation_channel.name}")
        except Exception as e:
            logger.error(f"Erreur lors de l'enregistrement de l'embed principal dans `persistent_messages`: {e}")
            await ctx.send("Erreur lors de l'enregistrement de la demande. Veuillez réessayer plus tard.", delete_after=10)
            return

        await ctx.send(f"Embed principal de demande de débannissement envoyé dans {moderation_channel.mention}.", delete_after=10)

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

    async def handle_deban_request_submission(self, interaction: discord.Interaction, user: discord.User, reason: str):
        """Gère la soumission du formulaire de demande de débannissement."""
        guild = interaction.guild
        if not guild:
            logger.error("Interaction sans guild.")
            await interaction.followup.send("Erreur interne. Veuillez contacter un administrateur.", ephemeral=True)
            return

        internal_server_id = await ModerationService.get_internal_server_id(guild.id)
        if not internal_server_id:
            logger.error(f"Aucun serveur trouvé avec guild_id {guild.id}.")
            await interaction.followup.send("Erreur interne. Veuillez contacter un administrateur.", ephemeral=True)
            return

        # Récupérer le salon de modération
        try:
            moderation_channel_id = await ModerationService.get_moderation_channel_id(internal_server_id)
            if not moderation_channel_id:
                logger.error(f"Aucun salon de modération configuré pour le serveur {guild.id}.")
                await interaction.followup.send("Aucun salon de modération configuré. Veuillez contacter un administrateur.", ephemeral=True)
                return
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du salon de modération: {e}")
            await interaction.followup.send("Erreur interne. Veuillez contacter un administrateur.", ephemeral=True)
            return

        moderation_channel = guild.get_channel(moderation_channel_id)
        if not moderation_channel:
            logger.error(f"Salon de modération avec l'ID {moderation_channel_id} introuvable.")
            await interaction.followup.send("Erreur interne. Veuillez contacter un administrateur.", ephemeral=True)
            return

        # Vérifier si l'utilisateur a déjà une demande en cours
        try:
            requester_internal_id = await ModerationService.get_or_create_user_id(user.id)
            if not requester_internal_id:
                await interaction.followup.send("Erreur interne. Veuillez contacter un administrateur.", ephemeral=True)
                return

            existing_requests = await ModerationService.get_persistent_messages_by_type(internal_server_id, "deban_request")
            for existing_request in existing_requests:
                requester_id = await ModerationService.get_requester_id(existing_request["message_id"])
                if requester_id == requester_internal_id:
                    await interaction.followup.send(
                        "Vous avez déjà une demande de débannissement en cours. Veuillez attendre qu'elle soit traitée avant d'en soumettre une nouvelle.",
                        ephemeral=True
                    )
                    return
        except Exception as e:
            logger.error(f"Erreur lors de la vérification des demandes en cours: {e}")
            await interaction.followup.send("Erreur interne. Veuillez contacter un administrateur.", ephemeral=True)
            return

        # Récupérer les informations de bannissement de l'utilisateur
        ban_info = await ModerationService.get_ban_info(user.id)
        if not ban_info:
            await interaction.followup.send("Vous n'êtes actuellement pas banni.", ephemeral=True)
            return

        # Récupérer les détails du bannissement
        ban_type = ban_info.get("type_name", "Inconnu")
        ban_reason = ban_info.get("ban_reason", "Aucune raison fournie")
        banned_at = ban_info.get("banned_at", "Inconnu")
        ban_end = ban_info.get("ban_end", "Permanent")
        banned_by_id = ban_info.get("banned_by")
        banned_by_discord_id = await ModerationService.get_discord_id(banned_by_id) if banned_by_id else None
        banned_by_user = guild.get_member(banned_by_discord_id) if banned_by_discord_id else None
        banned_by_mention = banned_by_user.mention if banned_by_user else "Utilisateur inconnu"

        # Créer l'embed de demande de débannissement individuelle
        embed = discord.Embed(
            title="📄 Nouvelle Demande de Déban",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="Utilisateur", value=f"{user} (`{user.id}`)", inline=False)
        embed.add_field(name="Raison de la Demande", value=reason, inline=False)
        embed.add_field(
            name="Détails du Bannissement",
            value=(
                f"**Type :** {ban_type}\n"
                f"**Raison :** {ban_reason}\n"
                f"**Banni(e) le :** {banned_at}\n"
                f"**Fin du ban :** {ban_end}\n"
                f"**Banni(e) par :** {banned_by_mention}"
            ),
            inline=False
        )
        embed.set_footer(text=f"Demande par {interaction.user}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)

        # Créer la vue avec les boutons Accepter et Refuser
        view = DebanRequestActionView(self, user_id=user.id, requester_id=requester_internal_id)

        # Envoyer l'embed dans le salon de modération
        try:
            message = await moderation_channel.send(embed=embed, view=view)
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi de la demande de débannissement individuelle: {e}")
            await interaction.followup.send("Erreur lors de l'envoi de la demande. Veuillez réessayer plus tard.", ephemeral=True)
            return

        # Enregistrer la demande individuelle dans la table `persistent_messages` avec message_type = 'deban_request'
        insert_query = """
        INSERT INTO persistent_messages (channel_id, message_id, message_type, created_at, guild_id, requester_id)
        VALUES ($1, $2, 'deban_request', NOW(), $3, $4)
        """
        try:
            await database.execute(insert_query, moderation_channel_id, message.id, internal_server_id, requester_internal_id)
            logger.info(f"Demande de débannissement individuelle envoyée et persistée avec ID {message.id} dans le canal {moderation_channel.name}")
        except Exception as e:
            logger.error(f"Erreur lors de l'enregistrement de la demande individuelle dans `persistent_messages`: {e}")
            await interaction.followup.send("Erreur lors de l'enregistrement de la demande. Veuillez réessayer plus tard.", ephemeral=True)
            return

        # Envoyer une confirmation à l'utilisateur
        await interaction.followup.send("Votre demande de débannissement a été envoyée.", ephemeral=True)

    async def process_accept(self, interaction: discord.Interaction, user_id: int, requester_internal_id: int):
        """Processus d'acceptation de la demande de débannissement."""
        # Déférer l'interaction immédiatement
        await interaction.response.defer(ephemeral=True)

        # Vérifier si l'utilisateur a les permissions nécessaires
        if not interaction.user.guild_permissions.ban_members:
            await interaction.followup.send("Vous n'avez pas les permissions nécessaires pour effectuer cette action.", ephemeral=True)
            return

        guild = interaction.guild
        if not guild:
            await interaction.followup.send("Erreur interne. Veuillez contacter un administrateur.", ephemeral=True)
            return

        # Obtenir le cog Moderation
        moderation_cog = self.bot.get_cog("Moderation")
        if not moderation_cog:
            logger.error("Cog de Modération non trouvé.")
            await interaction.followup.send("Erreur interne. Veuillez contacter un administrateur.", ephemeral=True)
            return

        # Appeler la méthode unban_member du cog Moderation
        try:
            await moderation_cog.unban_member(guild, user_id, reason="Débannissement via demande de débannissement.")
            logger.info(f"Demande de débannissement acceptée pour l'utilisateur ID {user_id} par {interaction.user}.")
        except Exception as e:
            logger.error(f"Erreur lors de l'appel à unban_member pour l'utilisateur {user_id}: {e}")
            await interaction.followup.send("Erreur lors du débannissement. Veuillez réessayer.", ephemeral=True)
            return

        # Supprimer le message persistant de la demande individuelle
        delete_query = """
        DELETE FROM persistent_messages
        WHERE message_id = $1 AND message_type = 'deban_request';
        """
        try:
            await database.execute(delete_query, interaction.message.id)
            logger.info(f"Message persistant de la demande individuelle ID {interaction.message.id} supprimé.")
        except Exception as e:
            logger.error(f"Erreur lors de la suppression du message persistant de la demande individuelle: {e}")

        # Supprimer le message d'origine dans le salon de modération
        try:
            await interaction.message.delete()
            logger.info(f"Message de demande individuelle ID {interaction.message.id} supprimé du salon.")
        except Exception as e:
            logger.error(f"Erreur lors de la suppression du message de demande individuelle: {e}")

        # Envoyer une confirmation éphémère au modérateur
        await interaction.followup.send("La demande de débannissement a été acceptée et l'utilisateur a été débanni.", ephemeral=True)

    async def process_reject(self, interaction: discord.Interaction, user_id: int, requester_internal_id: int):
        """Processus de refus de la demande de débannissement."""
        # Vérifier si l'utilisateur a les permissions nécessaires
        if not interaction.user.guild_permissions.ban_members:
            await interaction.followup.send("Vous n'avez pas les permissions nécessaires pour effectuer cette action.", ephemeral=True)
            return

        guild = interaction.guild
        if not guild:
            await interaction.followup.send("Erreur interne. Veuillez contacter un administrateur.", ephemeral=True)
            return

        # Informer l'utilisateur via DM
        try:
            discord_user_id = await ModerationService.get_discord_id(user_id)
            if discord_user_id:
                user_dm = await self.bot.fetch_user(discord_user_id)
                await user_dm.send(f"Votre demande de débannissement a été refusée sur le serveur **{guild.name}**.")
                logger.info(f"DM envoyé à l'utilisateur ID {user_id} pour le refus de la demande.")
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi du DM à l'utilisateur {user_id}: {e}")

        # Supprimer le message persistant de la demande individuelle
        delete_query = """
        DELETE FROM persistent_messages
        WHERE message_id = $1 AND message_type = 'deban_request';
        """
        try:
            await database.execute(delete_query, interaction.message.id)
            logger.info(f"Message persistant de la demande individuelle ID {interaction.message.id} supprimé.")
        except Exception as e:
            logger.error(f"Erreur lors de la suppression du message persistant de la demande individuelle: {e}")

        # Supprimer le message d'origine dans le salon de modération
        try:
            await interaction.message.delete()
            logger.info(f"Message de demande individuelle ID {interaction.message.id} supprimé du salon.")
        except Exception as e:
            logger.error(f"Erreur lors de la suppression du message de demande individuelle: {e}")

        # Envoyer une confirmation éphémère au modérateur
        await interaction.followup.send("La demande de débannissement a été refusée.", ephemeral=True)

    async def reload_persistent_views(self):
        """
        Recharge les vues persistantes pour les messages enregistrés.
        Cette méthode est appelée au démarrage du bot pour restaurer les interactions.
        """
        await self.bot.wait_until_ready()
        logger.info("Rechargement des vues persistantes pour les demandes de débannissement...")

        # Parcourir tous les serveurs (guilds) que le bot est membre
        for guild in self.bot.guilds:
            # Récupérer l'ID interne du serveur
            internal_server_id = await ModerationService.get_internal_server_id(guild.id)
            if not internal_server_id:
                logger.warning(f"Aucun ID interne trouvé pour guild_id {guild.id}.")
                continue

            # Récupérer l'embed principal de demande de débannissement
            message_data = await ModerationService.get_persistent_message(
                internal_server_id,
                "demande_deban"
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
                        logger.info(f"Vue ajoutée pour l'embed principal ID {message.id} dans le canal {channel.name}")
                    except discord.NotFound:
                        logger.warning(f"Message principal introuvable : {message_data['message_id']} dans le canal {channel.id}")
                    except Exception as e:
                        logger.error(f"Erreur lors du rechargement de la vue pour l'embed principal {message_data['message_id']}: {e}")

            # Récupérer toutes les demandes individuelles
            individual_requests = await ModerationService.get_persistent_messages_by_type(
                internal_server_id,
                "deban_request"
            )
            for request in individual_requests:
                channel = guild.get_channel(request["channel_id"])
                if not channel:
                    logger.warning(f"Canal introuvable : {request['channel_id']} dans guild_id={guild.id}")
                    continue
                try:
                    message = await channel.fetch_message(request["message_id"])
                    # Récupérer le requester_id pour le message individuel
                    requester_internal_id = await ModerationService.get_requester_id(request["message_id"])
                    if not requester_internal_id:
                        logger.warning(f"Aucun requester_id trouvé pour message_id {request['message_id']}.")
                        continue
                    # Récupérer le discord_id du requester
                    discord_id = await ModerationService.get_discord_id(requester_internal_id)
                    if not discord_id:
                        logger.warning(f"Aucun discord_id trouvé pour requester_internal_id {requester_internal_id}.")
                        continue
                    user = await self.bot.fetch_user(discord_id)
                    if not user:
                        logger.warning(f"Utilisateur introuvable avec discord_id {discord_id}.")
                        continue
                    view = DebanRequestActionView(self, user_id=user.id, requester_id=requester_internal_id)
                    self.bot.add_view(view, message_id=message.id)
                    logger.info(f"Vue ajoutée pour la demande individuelle ID {message.id} dans le canal {channel.name}")
                except discord.NotFound:
                    logger.warning(f"Message individuel introuvable : {request['message_id']} dans le canal {channel.id}")
                except Exception as e:
                    logger.error(f"Erreur lors du rechargement de la vue pour la demande individuelle {request['message_id']}: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(DebanManager(bot))
    logger.info("DebanManager Cog chargé avec succès.")
