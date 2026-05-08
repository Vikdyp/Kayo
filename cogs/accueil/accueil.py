# cogs/accueil/accueil.py
"""
Cog de bienvenue - UI Discord uniquement.
Aucun accès DB, aucun SQL. Appelle uniquement des services métier.
"""

import discord
from discord.ext import commands
import logging

from cogs.accueil.presenters import build_welcome_embed
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

        member_avatar_url = member.avatar.url if member.avatar else member.default_avatar.url
        bot_avatar_url = (
            self.bot.user.avatar.url
            if self.bot.user and self.bot.user.avatar
            else None
        )
        embed = build_welcome_embed(
            username=member.display_name,
            rules_mention=rules_mention,
            introductions_mention=introductions_mention,
            member_avatar_url=member_avatar_url,
            bot_avatar_url=bot_avatar_url,
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
