import discord
from discord.ext import commands
from discord import app_commands
from cogs.utils import load_json, save_json

class CleanManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="clean_all", description="Supprime tous les messages dans le salon")
    @app_commands.checks.has_role(1236375048252817418)  # Assurez-vous que l'ID du rôle est correct
    async def clean_all(self, interaction: discord.Interaction):
        """Demande confirmation avant de supprimer tous les messages."""
        await interaction.response.send_message("Êtes-vous sûr de vouloir supprimer tous les messages ?", view=self.ConfirmationView(interaction, None))

    @app_commands.command(name="clean_number", description="Supprime un nombre spécifié de messages")
    @app_commands.checks.has_role(1236375048252817418)  # Assurez-vous que l'ID du rôle est correct
    async def clean_number(self, interaction: discord.Interaction, count: int):
        """Demande confirmation avant de supprimer un nombre spécifié de messages."""
        await interaction.response.send_message(f"Êtes-vous sûr de vouloir supprimer {count} messages ?", view=self.ConfirmationView(interaction, count))

    class ConfirmationView(discord.ui.View):
        def __init__(self, interaction, count=None):
            super().__init__(timeout=20)  # Temps d'attente de 20 secondes
            self.interaction = interaction
            self.count = count

        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            """Vérifie si l'utilisateur a le rôle requis pour interagir avec les boutons."""
            role = discord.utils.get(interaction.guild.roles, id=1236375048252817418)
            if role in interaction.user.roles:
                return True
            await interaction.response.send_message("Vous n'avez pas la permission d'interagir avec cette commande.", ephemeral=True)
            return False

        @discord.ui.button(label="Confirmer", style=discord.ButtonStyle.green)
        async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
            if not await self.interaction_check(interaction):
                return
            try:
                if self.count is None:
                    await self.interaction.channel.purge()
                    await interaction.response.send_message("Tous les messages ont été supprimés.", ephemeral=True)
                else:
                    messages = [message async for message in self.interaction.channel.history(limit=self.count + 1)]
                    await self.interaction.channel.delete_messages(messages)
                    await interaction.response.send_message(f"{len(messages) - 1} messages ont été supprimés.", ephemeral=True)
            except discord.errors.NotFound:
                pass  # Ignorer les erreurs NotFound
            self.stop()

        @discord.ui.button(label="Annuler", style=discord.ButtonStyle.grey)
        async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
            if not await self.interaction_check(interaction):
                return
            try:
                await interaction.response.send_message("Action annulée.", ephemeral=True)
                await self.interaction.delete_original_response()
            except discord.errors.NotFound:
                pass  # Ignorer les erreurs NotFound
            self.stop()

        async def on_timeout(self):
            try:
                await self.interaction.delete_original_response()
            except discord.errors.NotFound:
                pass  # Ignorer les erreurs NotFound
            self.stop()

    @clean_all.error
    @clean_number.error
    async def clean_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingRole):
            await interaction.response.send_message("Vous n'avez pas la permission d'utiliser cette commande.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(CleanManager(bot))
