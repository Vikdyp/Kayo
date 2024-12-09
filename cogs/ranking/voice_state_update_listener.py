# cogs/ranking/voice_state_update_listener.py

import discord
from discord.ext import commands
import logging
from cogs.utilities.data_manager import DataManager

logger = logging.getLogger('discord.ranking.voice_state_update_listener')

class VoiceStateUpdateListener(commands.Cog):
    """MAJ du rôle de rang lors du changement d'état vocal."""

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
        logger.info("VoiceStateUpdateListener: Config et user_data chargées.")

    async def save_all_data(self):
        await self.data.save_json_file('data/user_data.json', self.user_data)
        logger.info("VoiceStateUpdateListener: user_data sauvegardées.")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        logger.info(f"MAJ état vocal: {member.name}.")
        user_id = str(member.id)
        if user_id in self.user_data:
            valorant_username = self.user_data[user_id]
            logger.info(f"{member.name} lié à {valorant_username}, maj du rôle.")
            assign_cog = self.bot.get_cog("AssignRankRole")
            if assign_cog:
                await assign_cog.assign_rank_role(member, valorant_username)
        else:
            logger.info(f"{member.name} pas de compte Valorant lié.")

async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceStateUpdateListener(bot))
    logger.info("VoiceStateUpdateListener Cog chargé avec succès.")
