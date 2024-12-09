# cogs/ranking/member_join_listener.py

import discord
from discord.ext import commands
import logging
from cogs.utilities.data_manager import DataManager

logger = logging.getLogger('discord.ranking.member_join_listener')

class MemberJoinListener(commands.Cog):
    """Invite les nouveaux membres à lier leur compte Valorant."""

    dependencies = []

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = DataManager()
        self.config = {}
        self.user_data = {}
        self.bot.loop.create_task(self.load_all_data())

    async def load_all_data(self):
        self.config = await self.data.get_config()
        self.user_data = await self.data.load_json_file('data/user_data.json')
        logger.info("MemberJoinListener: Config et user_data chargées.")

    async def save_all_data(self):
        await self.data.save_json_file('data/user_data.json', self.user_data)
        logger.info("MemberJoinListener: user_data sauvegardées.")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        logger.info(f'Nouveau membre: {member.name}')
        if str(member.id) not in self.user_data:
            await self.prompt_link_valorant(member)

    async def prompt_link_valorant(self, member: discord.Member):
        try:
            await member.send(
                "Bienvenue ! Pour accéder à ce serveur, veuillez lier votre compte Valorant avec `/link_valorant <url>`."
            )
            logger.info(f"DM envoyé à {member.name} pour lien Valorant.")
        except discord.Forbidden:
            logger.warning(f"Impossible d'envoyer un DM à {member.name}.")
        except Exception as e:
            logger.exception(f"Erreur envoi DM {member.name}: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(MemberJoinListener(bot))
    logger.info("MemberJoinListener Cog chargé avec succès.")
