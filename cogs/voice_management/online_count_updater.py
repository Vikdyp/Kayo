import discord
from discord import app_commands
from discord.ext import commands, tasks
import logging
from cogs.utilities.data_manager import DataManager

logger = logging.getLogger("discord.voice_management.online_count_updater")

class OnlineCountUpdater(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data = DataManager()
        self.update_task.start()

    @tasks.loop(minutes=5)
    async def update_task(self):
        config = await self.data.get_config()
        rank_channels = config.get("rank_channels", {})
        guild = self.bot.guilds[0] if self.bot.guilds else None
        if not guild:
            return
        for rank_name, channel_id in rank_channels.items():
            channel = guild.get_channel(channel_id)
            if channel:
                role = discord.utils.get(guild.roles, name=rank_name)
                if role:
                    online_count = sum(1 for m in role.members if m.status != discord.Status.offline)
                    new_name = f"{rank_name} {online_count} online"
                    if channel.name != new_name:
                        try:
                            await channel.edit(name=new_name)
                        except Exception as e:
                            logger.exception(f"Erreur lors de la maj du nom de {channel.name}: {e}")

    @update_task.before_loop
    async def before_update_task(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(OnlineCountUpdater(bot))
