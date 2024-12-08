# cogs/configuration/set_channel.py

import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Dict, Any

from cogs.utilities.utils import load_json, save_json

logger = logging.getLogger('discord.configuration.set_channel')


class SetChannel(commands.Cog):
    """Cog pour la commande de configuration de salon pour une action spécifique."""

    dependencies = []

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_file = 'data/config.json'
        self.config: Dict[str, Any] = {}
        self.bot.loop.create_task(self.load_config())

    async def load_config(self) -> None:
        """Charge la configuration depuis le fichier JSON."""
        self.config = await load_json(self.config_file)
        logger.info("SetChannel: Configuration chargée avec succès.")

    async def save_config(self) -> None:
        """Sauvegarde la configuration dans le fichier JSON."""
        await save_json(self.config, self.config_file)
        logger.info("SetChannel: Configuration sauvegardée avec succès.")

    @app_commands.command(name="set_channel", description="Configure un salon pour une action spécifique")
    @app_commands.describe(action="Nom de l'action (ex: report, notify)", channel="Salon Discord")
    @app_commands.default_permissions(administrator=True)
    async def set_channel(
        self,
        interaction: discord.Interaction,
        action: str,
        channel: discord.TextChannel
    ) -> None:
        """
        Configure un salon Discord pour une action spécifique.

        Parameters:
            interaction (discord.Interaction): L'interaction de l'utilisateur.
            action (str): Nom de l'action (ex: report, notify).
            channel (discord.TextChannel): Salon Discord à configurer.
        """
        self.config.setdefault("channels", {})
        self.config["channels"][action.lower()] = channel.id
        await self.save_config()
        await interaction.response.send_message(
            f"Salon `{channel.name}` configuré pour l'action `{action}` avec succès.",
            ephemeral=True
        )
        logger.info(f"Salon configuré: Action `{action}` -> Salon `{channel.name}` ({channel.id})")

    @set_channel.error
    async def set_channel_error(self, interaction: discord.Interaction, error: Exception) -> None:
        """Gère les erreurs liées à la commande set_channel."""
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "Vous n'avez pas la permission d'utiliser cette commande.",
                ephemeral=True
            )
            logger.warning(f"{interaction.user} a tenté d'utiliser /set_channel sans les permissions requises.")
        else:
            await interaction.response.send_message(
                "Une erreur est survenue lors de l'exécution de la commande.",
                ephemeral=True
            )
            logger.exception(f"Erreur lors de l'exécution de la commande set_channel par {interaction.user}: {error}")


async def setup(bot: commands.Bot) -> None:
    """Ajoute le Cog SetChannel au bot."""
    await bot.add_cog(SetChannel(bot))
    logger.info("SetChannel Cog chargé avec succès.")
