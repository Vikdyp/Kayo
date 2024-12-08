# cogs/ranking/member_join_listener.py

import discord
from discord.ext import commands
import logging

from ..utilities.utils import load_json, save_json

logger = logging.getLogger('discord.ranking.member_join_listener')


class MemberJoinListener(commands.Cog):
    """Cog pour écouter l'événement de l'arrivée d'un membre et initier la liaison de compte."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.user_data_file = 'data/user_data.json'
        self.config_file = 'data/config.json'
        self.config = {}
        self.user_data = {}
        self.bot.loop.create_task(self.load_all_data())

    async def load_all_data(self) -> None:
        """Charge la configuration et les données utilisateur depuis les fichiers JSON."""
        self.config = await load_json(self.config_file)
        self.user_data = await load_json(self.user_data_file)
        logger.info("MemberJoinListener: Configuration et données utilisateur chargées avec succès.")

    async def save_all_data(self) -> None:
        """Sauvegarde les données utilisateur dans le fichier JSON."""
        await save_json(self.user_data, self.user_data_file)
        logger.info("MemberJoinListener: Données utilisateur sauvegardées avec succès.")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Listener pour l'événement on_member_join."""
        logger.info(f'Nouveau membre: {member.name}')
        if str(member.id) not in self.user_data:
            await self.prompt_link_valorant(member)

    async def prompt_link_valorant(self, member: discord.Member) -> None:
        """
        Invite le membre à lier son compte Valorant via un message privé.

        Parameters:
            member (discord.Member): Membre Discord.
        """
        try:
            await member.send(
                "Bienvenue ! Pour accéder à ce serveur, veuillez lier votre compte Valorant en utilisant la commande `/link_valorant <valorant_tracker_url>`."
            )
            logger.info(f"Message envoyé à {member.name} pour lier le compte Valorant.")
        except discord.Forbidden:
            logger.warning(f"Impossible d'envoyer un message à {member.name}.")
        except Exception as e:
            logger.exception(f"Erreur lors de l'envoi du message à {member.name}: {e}")


async def setup(bot: commands.Bot) -> None:
    """Ajoute le Cog MemberJoinListener au bot."""
    await bot.add_cog(MemberJoinListener(bot))
    logger.info("MemberJoinListener Cog chargé avec succès.")
