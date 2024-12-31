# welcome_cog.py

from asyncio.log import logger
import discord
from discord.ext import commands

class StalkerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # ID du canal où envoyer le message
        self.channel_id = 1236437099310219336

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        """Envoie un message d'au revoir lorsque un membre quitte le serveur."""
        channel = self.bot.get_channel(self.channel_id)
        if channel is not None:
            username = f"{member.name}"
            message = f"{username} a quitté le serveur."
            await channel.send(message)
        else:
            print(f"Le canal avec l'ID {self.channel_id} n'a pas été trouvé.")

async def setup(bot: commands.Bot):
    await bot.add_cog(StalkerCog(bot))
    logger.info("StalkerCog chargé.")