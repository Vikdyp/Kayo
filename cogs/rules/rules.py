import discord
from discord.ext import commands, tasks
from utils.request_manager import enqueue_button_request
from utils.database import database
import logging

from cogs.rules.service.rules_services import (
    get_rules_channel_id,
    store_rules_message,
    get_persistent_message,
    delete_persistent_message,
    accept_rules_user  # Import de la fonction de service
)

logger = logging.getLogger("rules")

class AcceptRulesView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Accepter le règlement",
        style=discord.ButtonStyle.success,
        custom_id="button:accept_rules"
    )
    @enqueue_button_request("FAST")
    async def accept_rules_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        discord_id = interaction.user.id
        success = await accept_rules_user(discord_id)  # Utilisation de la fonction de service
        if success:
            await interaction.response.send_message(
                "Vous avez accepté le règlement. Bienvenue !",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "Une erreur est survenue lors de l'enregistrement. Veuillez réessayer plus tard.",
                ephemeral=True
            )

class RulesCog(commands.Cog):
    """Cog pour gérer les règles avec des boutons persistants."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("RulesCog initialisé.")
        self.bot.loop.create_task(self.reload_persistent_views())

    @commands.command(name="setup_rules")
    @commands.has_permissions(administrator=True)
    async def setup_rules(self, ctx: commands.Context):
        """
        Envoie l'embed du règlement et enregistre le message pour qu'il soit persistant.
        """
        logger.debug("Commande setup_rules exécutée.")
        guild_id = ctx.guild.id
        guild_name = ctx.guild.name
        logger.debug(f"Guild ID: {guild_id}, Guild Name: {guild_name}")

        # Récupérer ou configurer le salon des règles
        channel_id = await get_rules_channel_id(guild_id, guild_name)
        logger.debug(f"Channel ID récupéré: {channel_id}")
        if not channel_id:
            await ctx.send("Aucun salon 'rules' configuré pour cette guilde.", delete_after=10)
            logger.warning("Salon 'rules' non configuré.")
            return

        channel = self.bot.get_channel(channel_id)
        if not channel:
            await ctx.send("Le salon configuré pour les règles est introuvable.", delete_after=10)
            logger.error("Salon 'rules' introuvable.")
            return

        # Vérifier s'il existe déjà un message persistant
        existing_message = await get_persistent_message(guild_id, 'rules_embed', guild_name)
        logger.debug(f"Message persistant existant: {existing_message}")
        if existing_message:
            try:
                await channel.fetch_message(existing_message["message_id"])
                await ctx.send("Le règlement est déjà configuré dans ce salon.", delete_after=10)
                logger.info("Règlement déjà configuré.")
                return
            except discord.NotFound:
                logger.warning("Message persistant introuvable, en recréation...")

        # Créer l'embed des règles
        embed = discord.Embed(
            title="Règlement du Serveur",
            description=(
                "1. **Respect et courtoisie**\n"
                "   - Traitez tous les membres avec respect.\n"
                "2. **Pas de contenu interdit**\n"
                "   - Aucun contenu NSFW, harcèlement ou spamming n'est autorisé.\n"
                "3. **Le staff a toujours raison**\n"
                "   - Respectez les décisions du staff.\n\n"
                "**En cliquant sur 'Accepter le règlement', vous acceptez les conditions générales d'utilisation.**"
            ),
            color=discord.Color.green()
        )
        avatar_url = self.bot.user.avatar.url if self.bot.user.avatar else None
        embed.set_footer(
            text="N'hésite pas à demander de l'aide si tu as des questions !",
            icon_url=avatar_url
        )
        logger.debug("Embed des règles créé.")

        view = AcceptRulesView(self)

        # Envoyer l'embed avec le bouton
        try:
            message = await channel.send(embed=embed, view=view)
            logger.info(f"Message des règles envoyé avec ID: {message.id}")
        except discord.Forbidden:
            await ctx.send("Je n'ai pas les permissions nécessaires pour envoyer des messages dans ce salon.", delete_after=10)
            logger.error("Permission manquante pour envoyer un message dans le salon 'rules'.")
            return
        except Exception as e:
            await ctx.send("Une erreur est survenue lors de l'envoi du message.", delete_after=10)
            logger.error(f"Erreur lors de l'envoi du message des règles: {e}")
            return

        # Stocker le message dans la base
        success = await store_rules_message(guild_id, guild_name, channel.id, message.id)
        if success:
            await ctx.send(f"Règlement envoyé dans {channel.mention}.", delete_after=10)
            logger.info("Message des règles enregistré dans la base de données.")
        else:
            await ctx.send("Le règlement a été envoyé, mais une erreur est survenue lors de l'enregistrement.", delete_after=10)
            logger.error("Erreur lors de l'enregistrement du message des règles dans la base de données.")

    async def reload_persistent_views(self):
        """
        Recharge les vues persistantes pour les messages existants au démarrage.
        """
        await self.bot.wait_until_ready()
        logger.info("Rechargement des vues persistantes...")

        for guild in self.bot.guilds:
            guild_id = guild.id
            guild_name = guild.name

            # Récupérer le message persistant
            message_data = await get_persistent_message(guild_id, 'rules_embed', guild_name)
            if not message_data:
                continue

            channel = guild.get_channel(message_data["channel_id"])
            if not channel:
                logger.warning(f"Canal introuvable pour guild_id={guild_id}")
                continue

            try:
                message = await channel.fetch_message(message_data["message_id"])
                view = AcceptRulesView(self)
                self.bot.add_view(view, message_id=message.id)
                logger.info(f"Vue persistante ajoutée pour le message {message.id} dans le canal {channel.name}")
            except discord.NotFound:
                logger.warning(f"Message introuvable pour guild_id={guild_id}, suppression de la base.")
                await delete_persistent_message(guild_id, "rules_embed", guild_name)
            except Exception as e:
                logger.error(f"Erreur lors du rechargement des vues : {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("RulesCog prêt.")

    @setup_rules.error
    async def setup_rules_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("Vous n'avez pas les permissions nécessaires pour utiliser cette commande.", delete_after=10)
            logger.warning(f"{ctx.author} a tenté d'utiliser setup_rules sans permissions.")
        else:
            await ctx.send("Une erreur est survenue lors de l'exécution de la commande.", delete_after=10)
            logger.error(f"Erreur dans setup_rules : {error}")

async def setup(bot: commands.Bot):
    await bot.add_cog(RulesCog(bot))
    logger.info("RulesCog chargé.")
