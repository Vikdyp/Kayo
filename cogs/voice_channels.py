import discord
from discord.ext import commands
from discord import app_commands

class VoiceChannelsUtility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="list_channels", description="Lister tous les salons vocaux du serveur")
    async def list_channels(self, interaction: discord.Interaction):
        voice_channels = interaction.guild.voice_channels
        if voice_channels:
            channels_list = "\n".join([f"- {channel.name}" for channel in voice_channels])
            await interaction.response.send_message(f"Liste des salons vocaux :\n{channels_list}")
        else:
            await interaction.response.send_message("Aucun salon vocal n'a été trouvé sur ce serveur.")

    @app_commands.command(name="join", description="Rejoindre un salon vocal spécifique")
    @app_commands.describe(channel_name="Nom du salon vocal")
    async def join(self, interaction: discord.Interaction, channel_name: str):
        channel = discord.utils.get(interaction.guild.voice_channels, name=channel_name)
        if channel:
            try:
                if interaction.user.voice:
                    await interaction.user.move_to(channel)
                    await interaction.response.send_message(f"Vous avez été déplacé vers le salon vocal : {channel.name}")
                else:
                    await interaction.response.send_message("Vous devez être dans un salon vocal pour utiliser cette commande.")
            except discord.Forbidden:
                await interaction.response.send_message("Le bot n'a pas les permissions nécessaires pour déplacer l'utilisateur.")
        else:
            await interaction.response.send_message(f"Le salon vocal nommé '{channel_name}' n'existe pas.")

async def setup(bot):
    await bot.add_cog(VoiceChannelsUtility(bot))
