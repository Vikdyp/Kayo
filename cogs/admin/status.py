import discord
from discord import app_commands
from discord.ext import commands

class StatusManager(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        # S'exécute une seule fois pour définir la présence par défaut au démarrage
        if not hasattr(self.bot, "presence_set"):
            default_activity = "Perfect Team"
            await self.bot.change_presence(status=discord.Status.online, activity=discord.Game(name=default_activity))
            self.bot.presence_set = True

    @app_commands.command(name="setstatus", description="Modifie le status et l'activité du bot.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        status="Le nouveau status (online, idle, dnd, invisible)",
        activity="Nouveau message d'activité. Laisser vide pour utiliser 'Perfect Team'."
    )
    @app_commands.choices(status=[
        app_commands.Choice(name="online", value="online"),
        app_commands.Choice(name="idle", value="idle"),
        app_commands.Choice(name="dnd", value="dnd"),
        app_commands.Choice(name="invisible", value="invisible")
    ])
    async def set_status(self, interaction: discord.Interaction, status: app_commands.Choice[str], activity: str = None):
        valid_statuses = {
            "online": discord.Status.online,
            "idle": discord.Status.idle,
            "dnd": discord.Status.dnd,
            "invisible": discord.Status.invisible
        }
        new_status = valid_statuses.get(status.value)
        
        # Si aucune activité n'est fournie, on utilise "Perfect Team"
        if activity is None:
            default_activity = "Perfect Team"
            activity_obj = discord.Game(name=default_activity)
        else:
            activity_obj = discord.Game(name=activity)

        await self.bot.change_presence(status=new_status, activity=activity_obj)

        if activity is None:
            await interaction.response.send_message(
                f"Status modifié à **{status.value}** et l'activité est maintenant **Perfect Team**.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"Status modifié à **{status.value}** et l'activité est maintenant **{activity}**.",
                ephemeral=True
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(StatusManager(bot))
