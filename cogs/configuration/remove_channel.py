# cogs/configuration/remove_channel.py

import discord
from discord.ext import commands
from discord import app_commands
import logging

from ..utilities.utils import load_json, save_json

logger = logging.getLogger('discord.configuration.remove_channel')


class RemoveChannel(commands.Cog):
    """Cog pour la commande de suppression de configuration de salon pour une action."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_file = 'data/config.json'
        self.config = {}
        self.bot.loop.create_task(self.load_config())

    async def load_config(self) -> None:
        """Charge la configuration depuis le fichier JSON."""
        self.config = await load_json(self.config_file)
        logger.info("RemoveChannel: Configuration chargée avec succès.")

    async def save_config(self) -> None:
        """Sauvegarde la configuration dans le fichier JSON."""
        await save_json(self.config, self.config_file)
        logger.info("RemoveChannel: Configuration sauvegardée avec succès.")

    @app_commands.command(name="remove_channel", description="Supprime la configuration d'un salon pour une action")
    @app_commands.describe(action="Nom de l'action (ex: report, notify)")
    @app_commands.default_permissions(administrator=True)
    async def remove_channel(
        self,
        interaction: discord.Interaction,
        action: str
    ) -> None:
        """
        Supprime la configuration d'un salon pour une action spécifique.

        Parameters:
            interaction (discord.Interaction): L'interaction de l'utilisateur.
            action (str): Nom de l'action dont la configuration doit être supprimée.
        """
        channels = self.config.get("channels", {})
        action_lower = action.lower()
        if action_lower not in channels:
            await interaction.response.send_message(
                f"Aucune configuration trouvée pour l'action `{action}`.",
                ephemeral=True
            )
            logger.warning(f"{interaction.user} a tenté de supprimer une configuration inexistante pour l'action: {action}")
            return

        del self.config["channels"][action_lower]
        await self.save_config()
        await interaction.response.send_message(
            f"Configuration pour l'action `{action}` supprimée avec succès.",
            ephemeral=True
        )
        logger.info(f"Configuration de salon supprimée pour l'action `{action}`")

    @RemoveChannel.error
    async def remove_channel_error(self, interaction: discord.Interaction, error: Exception) -> None:
        """Gère les erreurs liées à la commande remove_channel."""
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "Vous n'avez pas la permission d'utiliser cette commande.",
                ephemeral=True
            )
            logger.warning(f"{interaction.user} a tenté d'utiliser /remove_channel sans les permissions requises.")
        else:
            await interaction.response.send_message(
                "Une erreur est survenue lors de l'exécution de la commande.",
                ephemeral=True
            )
            logger.exception(f"Erreur lors de l'exécution de la commande remove_channel par {interaction.user}: {error}")


async def setup(bot: commands.Bot) -> None:
    """Ajoute le Cog RemoveChannel au bot."""
    await bot.add_cog(RemoveChannel(bot))
    logger.info("RemoveChannel Cog chargé avec succès.")
