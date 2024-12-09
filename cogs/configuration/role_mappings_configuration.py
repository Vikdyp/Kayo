import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Dict, Any

from cogs.utilities.request_manager import enqueue_request
from cogs.utilities.data_manager import DataManager

logger = logging.getLogger('discord.configuration.role_mappings')

class RoleMappingsConfiguration(commands.Cog):
    """Cog pour gérer les mappings de rôles (script_role -> server_role)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = DataManager()
        self.config: Dict[str, Any] = {}
        self.bot.loop.create_task(self.load_config())

    async def load_config(self) -> None:
        self.config = await self.data.get_config()
        logger.info("RoleMappingsConfiguration: config chargée avec succès.")

    async def save_config(self) -> None:
        await self.data.save_config(self.config)
        logger.info("RoleMappingsConfiguration: config sauvegardée avec succès.")

    role_mappings_group = app_commands.Group(
        name="role_mappings",
        description="Gérer les mappings de rôles",
        default_permissions=discord.Permissions(administrator=True)
    )

    @role_mappings_group.command(name="get", description="Affiche tous les mappings de rôles")
    @enqueue_request()
    async def role_mappings_get(self, interaction: discord.Interaction):
        role_mappings = self.config.get("role_mappings", {})
        if not role_mappings:
            await interaction.followup.send("Aucun mapping de rôles défini.", ephemeral=True)
            return

        embed = discord.Embed(title="Mappings de Rôles", color=discord.Color.blue())
        for script_role, server_role_id in role_mappings.items():
            server_role = interaction.guild.get_role(server_role_id)
            if server_role:
                embed.add_field(name=script_role, value=server_role.name, inline=False)
            else:
                embed.add_field(name=script_role, value="Rôle non trouvé", inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)
        logger.info(f"{interaction.user} a demandé d'afficher les mappings de rôles.")

    @role_mappings_group.command(name="set", description="Mappez un rôle du script à un rôle du serveur")
    @app_commands.describe(script_role="Nom du rôle utilisé dans le script", server_role="Rôle sur le serveur Discord")
    @enqueue_request()
    async def role_mappings_set(self, interaction: discord.Interaction, script_role: str, server_role: discord.Role):
        self.config.setdefault("role_mappings", {})
        self.config["role_mappings"][script_role] = server_role.id
        await self.save_config()
        await interaction.followup.send(
            f"Rôle `{script_role}` mappé à `{server_role.name}` avec succès.",
            ephemeral=True
        )
        logger.info(f"Rôle mappé: {script_role} -> {server_role.name} ({server_role.id})")

    @role_mappings_group.command(name="remove", description="Supprime un mapping de rôle")
    @app_commands.describe(script_role="Nom du rôle utilisé dans le script")
    @enqueue_request()
    async def role_mappings_remove(self, interaction: discord.Interaction, script_role: str):
        role_mappings = self.config.get("role_mappings", {})
        if script_role not in role_mappings:
            await interaction.followup.send(
                f"Aucun mapping trouvé pour le rôle `{script_role}`.",
                ephemeral=True
            )
            logger.warning(f"{interaction.user} a tenté de supprimer un mapping inexistant: {script_role}")
            return

        del self.config["role_mappings"][script_role]
        await self.save_config()
        await interaction.followup.send(
            f"Mapping pour le rôle `{script_role}` supprimé avec succès.",
            ephemeral=True
        )
        logger.info(f"Mapping de rôle supprimé: {script_role}")

    @role_mappings_get.error
    @role_mappings_set.error
    @role_mappings_remove.error
    async def role_mappings_command_error(self, interaction: discord.Interaction, error: Exception):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.followup.send(
                "Vous n'avez pas la permission d'utiliser cette commande.",
                ephemeral=True
            )
            logger.warning(f"{interaction.user} a tenté d'utiliser une commande role_mappings sans les permissions requises.")
        else:
            await interaction.followup.send(
                "Une erreur est survenue lors de l'exécution de la commande.",
                ephemeral=True
            )
            logger.exception(f"Erreur lors de l'exécution d'une commande role_mappings par {interaction.user}: {error}")


async def setup(bot: commands.Bot):
    await bot.add_cog(RoleMappingsConfiguration(bot))
    logger.info("RoleMappingsConfiguration Cog chargé avec succès.")
