#cogs\utilities\embed_wizard.py
import discord
from discord.ext import commands
from discord import app_commands
from typing import Any

class EmbedWizardView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=600)
        self.title = None
        self.description = None
        self.final_channel = None

    @discord.ui.button(label="Définir le titre", style=discord.ButtonStyle.primary)
    async def set_title(self, interaction: Any, button: discord.ui.Button):
        await interaction.response.send_message("Veuillez entrer le titre de l'embed:", ephemeral=True)
        def check(msg):
            return msg.author == interaction.user and msg.channel == interaction.channel

        msg = await interaction.client.wait_for("message", check=check)
        self.title = msg.content
        await interaction.followup.send(f"Titre défini: {self.title}", ephemeral=True)

    @discord.ui.button(label="Définir la description", style=discord.ButtonStyle.primary)
    async def set_description(self, interaction: Any, button: discord.ui.Button):
        await interaction.response.send_message("Veuillez entrer la description:", ephemeral=True)
        def check(msg):
            return msg.author == interaction.user and msg.channel == interaction.channel

        msg = await interaction.client.wait_for("message", check=check)
        self.description = msg.content
        await interaction.followup.send("Description définie.", ephemeral=True)

    @discord.ui.button(label="Choisir un salon", style=discord.ButtonStyle.primary)
    async def choose_channel(self, interaction: Any, button: discord.ui.Button):
        await interaction.response.send_message("Mentionnez le salon (#exemple) où envoyer l'embed:", ephemeral=True)
        def check(msg):
            return msg.author == interaction.user and msg.channel == interaction.channel

        msg = await interaction.client.wait_for("message", check=check)
        if msg.channel_mentions:
            self.final_channel = msg.channel_mentions[0]
            await interaction.followup.send(f"Salon choisi: {self.final_channel.mention}", ephemeral=True)
        else:
            await interaction.followup.send("Aucun salon mentionné.", ephemeral=True)

    @discord.ui.button(label="Envoyer l'embed", style=discord.ButtonStyle.green)
    async def send_embed(self, interaction: Any, button: discord.ui.Button):
        if self.final_channel and self.title and self.description:
            embed = discord.Embed(title=self.title, description=self.description, color=discord.Color.blue())
            await self.final_channel.send(embed=embed)
            await interaction.response.send_message("Embed envoyé!", ephemeral=True)
        else:
            await interaction.response.send_message("Veuillez définir le titre, la description et le salon avant d'envoyer.", ephemeral=True)


class EmbedWizard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="embed_wizard", description="Crée un embed en plusieurs étapes")
    async def embed_wizard(self, interaction: Any):
        view = EmbedWizardView()
        await interaction.response.send_message("Lancement de l'assistant d'embed...", view=view, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(EmbedWizard(bot))
