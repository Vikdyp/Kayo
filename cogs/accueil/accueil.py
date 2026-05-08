# cogs/accueil/accueil.py
"""
Cog de bienvenue - UI Discord uniquement.
Aucun accès DB, aucun SQL. Appelle uniquement des services métier.
"""

import discord
from discord.ext import commands
import logging

from cogs.accueil.services import AccueilService

logger = logging.getLogger(__name__)


class WelcomeCog(commands.Cog):
    """Cog pour gérer les messages de bienvenue des nouveaux membres."""

    def __init__(self, bot: commands.Bot, accueil_service: AccueilService):
        self.bot = bot
        self._service = accueil_service
        logger.info("WelcomeCog initialisé.")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild_id = member.guild.id

        # Récupérer les channels via le service
        channels = await self._service.get_welcome_channels(guild_id)

        if not channels.welcome_channel_id:
            logger.warning(f"Aucun salon d'accueil configuré pour la guilde {guild_id}.")
            return

        welcome_channel = self.bot.get_channel(channels.welcome_channel_id)
        if not welcome_channel:
            logger.error(
                f"Salon avec l'ID {channels.welcome_channel_id} introuvable dans la guilde {guild_id}."
            )
            return

        # Préparer les mentions des channels
        rules_mention = (
            f"<#{channels.rules_channel_id}>"
            if channels.rules_channel_id
            else "le canal des règles"
        )
        introductions_mention = (
            f"<#{channels.introductions_channel_id}>"
            if channels.introductions_channel_id
            else "le canal de présentation"
        )

        # Récupérer le pseudo à afficher
        username = member.display_name

        # Créer l'embed de bienvenue
        embed = discord.Embed(
            title="🎉 Bienvenue sur le serveur ! 🎉",
            description=(
                f"Salut **{username}** ! Nous sommes ravis de t'accueillir parmi nous. 🎉\n\n"
                "Pour bien démarrer, voici quelques informations importantes :\n"
                f"• **Règles du serveur** : Assure-toi de lire {rules_mention}.\n"
                f"• **Découvre le serveur** : Va dans {introductions_mention} pour en apprendre davantage sur notre communauté.\n\n"
            ),
            color=discord.Color.blue(),
        )

        # Gérer l'image de l'avatar
        if member.avatar:
            embed.set_thumbnail(url=member.avatar.url)
        else:
            embed.set_thumbnail(url=member.default_avatar.url)

        if self.bot.user.avatar:
            embed.set_footer(
                text="N'hésite pas à demander de l'aide si tu as des questions !",
                icon_url=self.bot.user.avatar.url,
            )

        try:
            await welcome_channel.send(embed=embed)
            logger.info(f"Message de bienvenue envoyé à {member} dans {welcome_channel.name}.")
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi du message de bienvenue : {e}")


async def setup(bot: commands.Bot):
    accueil_service = getattr(bot, "accueil_service", None)
    if accueil_service is None:
        logger.error("accueil_service non initialisé. WelcomeCog ne sera pas chargé.")
        return

    await bot.add_cog(WelcomeCog(bot, accueil_service))
    logger.info("WelcomeCog chargé.")
