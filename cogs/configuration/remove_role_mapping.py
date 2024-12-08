# cogs/configuration/remove_role_mapping.py

import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Dict, Any

from cogs.utilities.utils import load_json, save_json

logger = logging.getLogger('discord.configuration.remove_role_mapping')


class RemoveRoleMapping(commands.Cog):
    """Cog pour la commande de suppression de mapping de rôle."""

    dependencies = []

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_file = 'data/config.json'
        self.config: Dict[str, Any] = {}
        self.bot.loop.create_task(self.load_config())

    async def load_config(self) -> None:
        """Charge la configuration depuis le fichier JSON."""
        self.config = await load_json(self.config_file)
        logger.info("RemoveRoleMapping: Configuration chargée avec succès.")

    async def save_config(self) -> None:
        """Sauvegarde la configuration dans le fichier JSON."""
        await save_json(self.config, self.config_file)
        logger.info("RemoveRoleMapping: Configuration sauvegardée avec succès.")

    @app_commands.command(name="remove_role_mapping", description="Supprime un mapping de rôle")
    @app_commands.describe(script_role="Nom du rôle utilisé dans le script")
    @app_commands.default_permissions(administrator=True)
    async def remove_role_mapping(
        self,
        interaction: discord.Interaction,
        script_role: str
    ) -> None:
        """
        Supprime un mapping de rôle spécifique.

        Parameters:
            interaction (discord.Interaction): L'interaction de l'utilisateur.
            script_role (str): Nom du rôle utilisé dans le script à supprimer.
        """
        role_mappings = self.config.get("role_mappings", {})
        if script_role not in role_mappings:
            await interaction.response.send_message(
                f"Aucun mapping trouvé pour le rôle `{script_role}`.",
                ephemeral=True
            )
            logger.warning(f"{interaction.user} a tenté de supprimer un mapping inexistant: {script_role}")
            return

        del self.config["role_mappings"][script_role]
        await self.save_config()
        await interaction.response.send_message(
            f"Mapping pour le rôle `{script_role}` supprimé avec succès.",
            ephemeral=True
        )
        logger.info(f"Mapping de rôle supprimé: {script_role}")

    @remove_role_mapping.error
    async def remove_role_mapping_error(self, interaction: discord.Interaction, error: Exception) -> None:
        """Gère les erreurs liées à la commande remove_role_mapping."""
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "Vous n'avez pas la permission d'utiliser cette commande.",
                ephemeral=True
            )
            logger.warning(f"{interaction.user} a tenté d'utiliser /remove_role_mapping sans les permissions requises.")
        else:
            await interaction.response.send_message(
                "Une erreur est survenue lors de l'exécution de la commande.",
                ephemeral=True
            )
            logger.exception(f"Erreur lors de l'exécution de la commande remove_role_mapping par {interaction.user}: {error}")


async def setup(bot: commands.Bot) -> None:
    """Ajoute le Cog RemoveRoleMapping au bot."""
    await bot.add_cog(RemoveRoleMapping(bot))
    logger.info("RemoveRoleMapping Cog chargé avec succès.")
