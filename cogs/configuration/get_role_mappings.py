# cogs/configuration/get_role_mappings.py

import discord
from discord.ext import commands
from discord import app_commands
import logging

from ..utilities.utils import load_json, save_json

logger = logging.getLogger('discord.configuration.get_role_mappings')


class GetRoleMappings(commands.Cog):
    """Cog pour la commande d'affichage des mappings de rôles."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_file = 'data/config.json'
        self.config = {}
        self.bot.loop.create_task(self.load_config())

    async def load_config(self) -> None:
        """Charge la configuration depuis le fichier JSON."""
        self.config = await load_json(self.config_file)
        logger.info("GetRoleMappings: Configuration chargée avec succès.")

    @app_commands.command(name="get_role_mappings", description="Affiche tous les mappings de rôles")
    @app_commands.default_permissions(administrator=True)
    async def get_role_mappings(self, interaction: discord.Interaction) -> None:
        """
        Affiche tous les mappings de rôles configurés.

        Parameters:
            interaction (discord.Interaction): L'interaction de l'utilisateur.
        """
        role_mappings = self.config.get("role_mappings", {})
        if not role_mappings:
            await interaction.response.send_message("Aucun mapping de rôles défini.", ephemeral=True)
            return

        embed = discord.Embed(title="Mappings de Rôles", color=discord.Color.blue())
        for script_role, server_role_id in role_mappings.items():
            server_role = interaction.guild.get_role(server_role_id)
            if server_role:
                embed.add_field(name=script_role, value=server_role.name, inline=False)
            else:
                embed.add_field(name=script_role, value="Rôle non trouvé", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)
        logger.info(f"{interaction.user} a demandé d'afficher les mappings de rôles.")


@GetRoleMappings.error
async def get_role_mappings_error(self, interaction: discord.Interaction, error: Exception) -> None:
    """Gère les erreurs liées à la commande get_role_mappings."""
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "Vous n'avez pas la permission d'utiliser cette commande.",
            ephemeral=True
        )
        logger.warning(f"{interaction.user} a tenté d'utiliser /get_role_mappings sans les permissions requises.")
    else:
        await interaction.response.send_message(
            "Une erreur est survenue lors de l'exécution de la commande.",
            ephemeral=True
        )
        logger.exception(f"Erreur lors de l'exécution de la commande get_role_mappings par {interaction.user}: {error}")


async def setup(bot: commands.Bot) -> None:
    """Ajoute le Cog GetRoleMappings au bot."""
    await bot.add_cog(GetRoleMappings(bot))
    logger.info("GetRoleMappings Cog chargé avec succès.")
