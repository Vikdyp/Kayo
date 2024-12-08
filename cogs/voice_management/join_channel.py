# cogs/voice_management/join_channel.py

import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Optional

from ..utilities.utils import load_json, save_json  # Assurez-vous que ces fonctions sont asynchrones

logger = logging.getLogger('discord.voice_management.join_channel')


class JoinChannel(commands.Cog):
    """Cog pour la commande de déplacement vers un salon vocal."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_file = 'data/config.json'
        self.config: dict = {}
        self.bot.loop.create_task(self.load_config())

    async def load_config(self) -> None:
        """Charge la configuration depuis le fichier JSON."""
        self.config = await load_json(self.config_file)
        logger.info("JoinChannel: Configuration chargée avec succès.")

    @app_commands.command(name="join", description="Rejoindre un salon vocal spécifique")
    @app_commands.describe(channel_name="Nom du salon vocal")
    async def join(self, interaction: discord.Interaction, channel_name: str) -> None:
        """
        Déplace l'utilisateur vers un salon vocal spécifique.

        Parameters:
            interaction (discord.Interaction): L'interaction de l'utilisateur.
            channel_name (str): Nom du salon vocal à rejoindre.
        """
        channel = discord.utils.get(interaction.guild.voice_channels, name=channel_name)
        if channel:
            # Vérifier si le bot a les permissions nécessaires
            permissions = channel.permissions_for(interaction.guild.me)
            if not permissions.move_members:
                await interaction.response.send_message(
                    "Je n'ai pas les permissions nécessaires pour déplacer les membres.",
                    ephemeral=True
                )
                logger.warning(f"Permission refusée pour déplacer les membres vers {channel.name}.")
                return

            # Vérifier si l'utilisateur est dans un salon vocal
            if interaction.user.voice and interaction.user.voice.channel:
                try:
                    await interaction.user.move_to(channel)
                    await interaction.response.send_message(
                        f"Vous avez été déplacé vers le salon vocal : {channel.name}",
                        ephemeral=True
                    )
                    logger.info(f"{interaction.user} a été déplacé vers {channel.name}.")
                except discord.Forbidden:
                    await interaction.response.send_message(
                        "Je n'ai pas les permissions nécessaires pour déplacer l'utilisateur.",
                        ephemeral=True
                    )
                    logger.error(f"Permission refusée pour déplacer {interaction.user} vers {channel.name}.")
                except discord.HTTPException as e:
                    await interaction.response.send_message(
                        "Une erreur est survenue lors du déplacement.",
                        ephemeral=True
                    )
                    logger.exception(f"Erreur HTTP lors du déplacement de {interaction.user} vers {channel.name}: {e}")
            else:
                await interaction.response.send_message(
                    "Vous devez être dans un salon vocal pour utiliser cette commande.",
                    ephemeral=True
                )
                logger.info(f"{interaction.user} a tenté de rejoindre {channel.name} sans être dans un salon vocal.")
        else:
            await interaction.response.send_message(
                f"Le salon vocal nommé '{channel_name}' n'existe pas.",
                ephemeral=True
            )
            logger.warning(f"{interaction.user} a tenté de rejoindre un salon vocal inexistant: {channel_name}.")

    @join.error
    async def join_error(self, interaction: discord.Interaction, error: Exception) -> None:
        """Gère les erreurs liées à la commande join."""
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "Vous n'avez pas la permission d'utiliser cette commande.",
                ephemeral=True
            )
            logger.warning(f"{interaction.user} a tenté d'utiliser /join sans permissions.")
        else:
            await interaction.response.send_message(
                "Une erreur est survenue lors de l'exécution de la commande.",
                ephemeral=True
            )
            logger.exception(f"Erreur lors de l'exécution de /join par {interaction.user}: {error}")


async def setup(bot: commands.Bot) -> None:
    """Ajoute le Cog JoinChannel au bot."""
    await bot.add_cog(JoinChannel(bot))
    logger.info("JoinChannel Cog chargé avec succès.")
