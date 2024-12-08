# cogs/voice_management/list_channels.py

import discord
from discord.ext import commands
from discord import app_commands
import logging

from ..utilities.utils import load_json, save_json  # Assurez-vous que ces fonctions sont asynchrones

logger = logging.getLogger('discord.voice_management.list_channels')


class ListChannels(commands.Cog):
    """Cog pour la commande de listage des salons vocaux."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_file = 'data/config.json'
        self.config: dict = {}
        self.bot.loop.create_task(self.load_config())

    async def load_config(self) -> None:
        """Charge la configuration depuis le fichier JSON."""
        self.config = await load_json(self.config_file)
        logger.info("ListChannels: Configuration chargée avec succès.")

    @app_commands.command(name="list_channels", description="Lister tous les salons vocaux du serveur")
    async def list_channels(self, interaction: discord.Interaction) -> None:
        """
        Liste tous les salons vocaux du serveur.

        Parameters:
            interaction (discord.Interaction): L'interaction de l'utilisateur.
        """
        voice_channels = interaction.guild.voice_channels
        if voice_channels:
            channels_list = "\n".join([f"- {channel.name}" for channel in voice_channels])
            embed = discord.Embed(
                title="Liste des Salons Vocaux",
                description=channels_list,
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed)
            logger.info(f"{interaction.user} a listé les salons vocaux.")
        else:
            await interaction.response.send_message(
                "Aucun salon vocal n'a été trouvé sur ce serveur.",
                ephemeral=True
            )
            logger.info(f"{interaction.user} a tenté de lister les salons vocaux, mais aucun n'a été trouvé.")

    @list_channels.error
    async def list_channels_error(self, interaction: discord.Interaction, error: Exception) -> None:
        """Gère les erreurs liées à la commande list_channels."""
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "Vous n'avez pas la permission d'utiliser cette commande.",
                ephemeral=True
            )
            logger.warning(f"{interaction.user} a tenté d'utiliser /list_channels sans permissions.")
        else:
            await interaction.response.send_message(
                "Une erreur est survenue lors de l'exécution de la commande.",
                ephemeral=True
            )
            logger.exception(f"Erreur lors de l'exécution de /list_channels par {interaction.user}: {error}")


async def setup(bot: commands.Bot) -> None:
    """Ajoute le Cog ListChannels au bot."""
    await bot.add_cog(ListChannels(bot))
    logger.info("ListChannels Cog chargé avec succès.")
