import discord
from discord import app_commands
from discord.ext import commands

from cogs.admin.presenters import DEFAULT_ACTIVITY, format_status_update_message


DISCORD_STATUS_BY_KEY = {
    "online": discord.Status.online,
    "idle": discord.Status.idle,
    "dnd": discord.Status.dnd,
    "invisible": discord.Status.invisible,
}

STATUS_CHOICES = [
    app_commands.Choice(name=status_key, value=status_key)
    for status_key in DISCORD_STATUS_BY_KEY
]


class StatusManager(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        # S'exécute une seule fois pour définir la présence par défaut au démarrage
        if not hasattr(self.bot, "presence_set"):
            await self.bot.change_presence(
                status=discord.Status.online,
                activity=discord.Game(name=DEFAULT_ACTIVITY),
            )
            self.bot.presence_set = True

    @app_commands.command(name="setstatus", description="Modifie le status et l'activité du bot.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        status="Le nouveau status (online, idle, dnd, invisible)",
        activity="Nouveau message d'activité. Laisser vide pour utiliser 'Perfect Team'."
    )
    @app_commands.choices(status=STATUS_CHOICES)
    async def set_status(self, interaction: discord.Interaction, status: app_commands.Choice[str], activity: str = None):
        new_status = DISCORD_STATUS_BY_KEY.get(status.value)
        if not new_status:
            await interaction.response.send_message("Status invalide.", ephemeral=True)
            return

        activity_obj = discord.Game(name=activity or DEFAULT_ACTIVITY)

        await self.bot.change_presence(status=new_status, activity=activity_obj)
        await interaction.response.send_message(
            format_status_update_message(status.value, activity),
            ephemeral=True,
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(StatusManager(bot))
