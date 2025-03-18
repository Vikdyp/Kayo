import discord
from discord import app_commands
from discord.ext import commands

class StatusManager(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="setstatus", description="Modifie le status et l'activité du bot.")
    @app_commands.describe(
        status="Le nouveau status (online, idle, dnd, invisible)",
        activity="Nouveau message d'activité. Laisser vide pour conserver l'activité actuelle."
    )
    @app_commands.choices(status=[
        app_commands.Choice(name="online", value="online"),
        app_commands.Choice(name="idle", value="idle"),
        app_commands.Choice(name="dnd", value="dnd"),
        app_commands.Choice(name="invisible", value="invisible")
    ])
    async def set_status(self, interaction: discord.Interaction, status: app_commands.Choice[str], activity: str = None):
        # Vérifier que l'utilisateur a les droits d'admin dans la guilde
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Vous n'avez pas la permission d'utiliser cette commande.", ephemeral=True)
            return

        valid_statuses = {
            "online": discord.Status.online,
            "idle": discord.Status.idle,
            "dnd": discord.Status.dnd,
            "invisible": discord.Status.invisible
        }
        new_status = valid_statuses.get(status.value)
        # Conserver l'activité actuelle si aucun nouveau message n'est fourni
        if activity is None:
            # Utiliser l'activité actuelle (peut être None si aucune n'a été définie)
            activity_obj = self.bot.activity
        else:
            activity_obj = discord.Game(name=activity)

        await self.bot.change_presence(status=new_status, activity=activity_obj)

        # Répondre à l'interaction en indiquant ce qui a été modifié
        if activity is None:
            await interaction.response.send_message(
                f"Status modifié à **{status.value}** et l'activité reste inchangée.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"Status modifié à **{status.value}** et l'activité est maintenant **{activity}**.",
                ephemeral=True
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(StatusManager(bot))
