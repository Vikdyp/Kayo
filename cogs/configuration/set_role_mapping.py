# cogs/configuration/set_role_mapping.py

import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Dict, Any

from cogs.utilities.utils import load_json, save_json

logger = logging.getLogger('discord.configuration.set_role_mapping')


class SetRoleMapping(commands.Cog):
    """Cog pour la commande de mapping de rôle."""

    dependencies = []

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_file = 'data/config.json'
        self.config: Dict[str, Any] = {}
        self.bot.loop.create_task(self.load_config())

    async def load_config(self) -> None:
        """Charge la configuration depuis le fichier JSON."""
        self.config = await load_json(self.config_file)
        logger.info("SetRoleMapping: Configuration chargée avec succès.")

    async def save_config(self) -> None:
        """Sauvegarde la configuration dans le fichier JSON."""
        await save_json(self.config, self.config_file)
        logger.info("SetRoleMapping: Configuration sauvegardée avec succès.")

    @app_commands.command(name="set_role_mapping", description="Mappez un rôle du script à un rôle du serveur")
    @app_commands.describe(script_role="Nom du rôle utilisé dans le script", server_role="Rôle sur le serveur Discord")
    @app_commands.default_permissions(administrator=True)
    async def set_role_mapping(
        self,
        interaction: discord.Interaction,
        script_role: str,
        server_role: discord.Role
    ) -> None:
        """
        Mappe un rôle utilisé dans le script à un rôle du serveur Discord.

        Parameters:
            interaction (discord.Interaction): L'interaction de l'utilisateur.
            script_role (str): Nom du rôle utilisé dans le script.
            server_role (discord.Role): Rôle sur le serveur Discord à mapper.
        """
        self.config.setdefault("role_mappings", {})
        self.config["role_mappings"][script_role] = server_role.id
        await self.save_config()
        await interaction.response.send_message(
            f"Rôle `{script_role}` mappé à `{server_role.name}` avec succès.",
            ephemeral=True
        )
        logger.info(f"Rôle mappé: {script_role} -> {server_role.name} ({server_role.id})")

    @set_role_mapping.error
    async def set_role_mapping_error(self, interaction: discord.Interaction, error: Exception) -> None:
        """Gère les erreurs liées à la commande set_role_mapping."""
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "Vous n'avez pas la permission d'utiliser cette commande.",
                ephemeral=True
            )
            logger.warning(f"{interaction.user} a tenté d'utiliser /set_role_mapping sans les permissions requises.")
        else:
            await interaction.response.send_message(
                "Une erreur est survenue lors de l'exécution de la commande.",
                ephemeral=True
            )
            logger.exception(f"Erreur lors de l'exécution de la commande set_role_mapping par {interaction.user}: {error}")


async def setup(bot: commands.Bot) -> None:
    """Ajoute le Cog SetRoleMapping au bot."""
    await bot.add_cog(SetRoleMapping(bot))
    logger.info("SetRoleMapping Cog chargé avec succès.")
