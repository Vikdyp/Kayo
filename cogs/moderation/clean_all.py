# cogs/moderation/clean_number.py

import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Dict, Any

from cogs.utilities.utils import load_json, save_json

logger = logging.getLogger('discord.moderation.clean_number')


class CleanNumber(commands.Cog):
    """Cog pour la commande de nettoyage de messages numérotés."""

    dependencies = []

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_file = 'data/moderation_config.json'
        self.config: Dict[str, Any] = {}
        self.bot.loop.create_task(self.load_config())

    async def load_config(self) -> None:
        """Charge la configuration depuis le fichier JSON."""
        self.config = await load_json(self.config_file)
        logger.info("CleanNumber: Configuration chargée avec succès.")

    @app_commands.command(name="clean_number", description="Nettoie les messages numérotés dans un canal")
    @app_commands.describe(channel="Salon Discord à nettoyer", number="Nombre de messages à nettoyer")
    @app_commands.default_permissions(manage_messages=True)
    async def clean_number(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        number: int
    ) -> None:
        """
        Nettoie un nombre spécifique de messages dans un salon Discord.

        Parameters:
            interaction (discord.Interaction): L'interaction de l'utilisateur.
            channel (discord.TextChannel): Salon Discord à nettoyer.
            number (int): Nombre de messages à nettoyer.
        """
        deleted = await channel.purge(limit=number)
        await interaction.response.send_message(
            f"{len(deleted)} messages ont été supprimés dans {channel.mention}.",
            ephemeral=True
        )
        logger.info(f"{interaction.user} a nettoyé {len(deleted)} messages dans {channel.name}.")

    @clean_number.error
    async def clean_number_error(self, interaction: discord.Interaction, error: Exception) -> None:
        """Gère les erreurs liées à la commande clean_number."""
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "Vous n'avez pas la permission d'utiliser cette commande.",
                ephemeral=True
            )
            logger.warning(f"{interaction.user} a tenté d'utiliser /clean_number sans les permissions requises.")
        else:
            await interaction.response.send_message(
                "Une erreur est survenue lors de l'exécution de la commande.",
                ephemeral=True
            )
            logger.exception(f"Erreur lors de l'exécution de la commande clean_number par {interaction.user}: {error}")


async def setup(bot: commands.Bot) -> None:
    """Ajoute le Cog CleanNumber au bot."""
    await bot.add_cog(CleanNumber(bot))
    logger.info("CleanNumber Cog chargé avec succès.")
