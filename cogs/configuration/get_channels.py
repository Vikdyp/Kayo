# cogs/configuration/get_channels.py

import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Dict, Any

from cogs.utilities.utils import load_json, save_json

logger = logging.getLogger('discord.configuration.get_channels')


class GetChannels(commands.Cog):
    """Cog pour la commande d'affichage des salons configurés."""

    dependencies = []


    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_file = 'data/config.json'
        self.config: Dict[str, Any] = {}
        self.bot.loop.create_task(self.load_config())

    async def load_config(self) -> None:
        """Charge la configuration depuis le fichier JSON."""
        self.config = await load_json(self.config_file)
        logger.info("GetChannels: Configuration chargée avec succès.")

    @app_commands.command(name="get_channels", description="Affiche les salons configurés")
    @app_commands.default_permissions(administrator=True)
    async def get_channels(self, interaction: discord.Interaction) -> None:
        """
        Affiche les salons configurés pour les actions spécifiques.

        Parameters:
            interaction (discord.Interaction): L'interaction de l'utilisateur.
        """
        channels = self.config.get("channels", {})
        if not channels:
            await interaction.response.send_message("Aucun salon configuré.", ephemeral=True)
            return

        embed = discord.Embed(title="Salons Configurés", color=discord.Color.green())
        for action, channel_id in channels.items():
            channel = interaction.guild.get_channel(channel_id)
            if channel:
                embed.add_field(name=action.capitalize(), value=channel.mention, inline=False)
            else:
                embed.add_field(name=action.capitalize(), value="Salon non trouvé", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)
        logger.info(f"{interaction.user} a demandé d'afficher les salons configurés.")

    @get_channels.error
    async def get_channels_error(self, interaction: discord.Interaction, error: Exception) -> None:
        """Gère les erreurs liées à la commande get_channels."""
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "Vous n'avez pas la permission d'utiliser cette commande.",
                ephemeral=True
            )
            logger.warning(f"{interaction.user} a tenté d'utiliser /get_channels sans les permissions requises.")
        else:
            await interaction.response.send_message(
                "Une erreur est survenue lors de l'exécution de la commande.",
                ephemeral=True
            )
            logger.exception(f"Erreur lors de l'exécution de la commande get_channels par {interaction.user}: {error}")


async def setup(bot: commands.Bot) -> None:
    """Ajoute le Cog GetChannels au bot."""
    await bot.add_cog(GetChannels(bot))
    logger.info("GetChannels Cog chargé avec succès.")
