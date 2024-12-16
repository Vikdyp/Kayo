import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Optional

from utils.request_manager import enqueue_request
from cogs.configuration.services.role_service import RoleService

logger = logging.getLogger('roles_configuration')


class RolesConfiguration(commands.Cog):
    """Cog pour gérer la configuration des rôles."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("RolesConfiguration initialisé.")

    PREDEFINED_ROLES = [
        "bon joueur", "booster", "ban", "mauvais joueur", "admin",
        "fer", "bronze", "argent", "or", "platine", "diamant", "ascendant",
        "immortel", "radiant", "sentinel", "duelist", "controller", "initiator", "fill"
    ]

    ROLE_CHOICES = [
        app_commands.Choice(name=role.capitalize(), value=role)
        for role in PREDEFINED_ROLES
    ]

    @app_commands.command(name="roles", description="Exécute des actions sur la configuration des rôles.")
    @app_commands.describe(
        action="Action à effectuer",
        role_name="Nom du rôle (nécessaire pour 'set' ou 'remove')",
        role="Rôle Discord (nécessaire pour 'set')"
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Afficher les rôles configurés", value="get"),
            app_commands.Choice(name="Configurer un rôle", value="set"),
            app_commands.Choice(name="Supprimer un rôle", value="remove")
        ],
        role_name=ROLE_CHOICES
    )
    @enqueue_request()
    async def roles_execute(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        role_name: Optional[app_commands.Choice[str]] = None,
        role: Optional[discord.Role] = None
    ):
        """Exécute une action de configuration de rôle en fonction de l'option spécifiée."""
        try:
            if not interaction.guild:
                await interaction.followup.send(
                    "Cette commande doit être exécutée dans un serveur.", ephemeral=True
                )
                return

            if action.value == "get":
                roles = await RoleService.get_roles_config(interaction.guild.id)
                if not roles:
                    await interaction.followup.send("Aucun rôle configuré.", ephemeral=True)
                    return

                embed = discord.Embed(title="Rôles Configurés", color=discord.Color.blue())
                for role_key, role_id in roles.items():
                    guild_role = interaction.guild.get_role(role_id)
                    embed.add_field(
                        name=role_key.capitalize(),
                        value=guild_role.name if guild_role else "Rôle non trouvé",
                        inline=False
                    )
                await interaction.followup.send(embed=embed, ephemeral=True)

            elif action.value == "set":
                if not role_name or not role:
                    await interaction.followup.send(
                        "Veuillez spécifier un rôle et un rôle Discord pour cette action.", ephemeral=True
                    )
                    return

                success = await RoleService.set_role_for_action(
                    interaction.guild.id, role_name.value, role.id
                )
                if success:
                    await interaction.followup.send(
                        f"Rôle {role.name} configuré pour {role_name.value.capitalize()}.", ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "Une erreur est survenue lors de la configuration.", ephemeral=True
                    )

            elif action.value == "remove":
                if not role_name:
                    await interaction.followup.send(
                        "Veuillez spécifier un rôle pour cette action.", ephemeral=True
                    )
                    return

                success = await RoleService.remove_role_for_action(
                    interaction.guild.id, role_name.value
                )
                if success:
                    await interaction.followup.send(
                        f"Configuration pour {role_name.value.capitalize()} supprimée.", ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "Aucune configuration trouvée pour ce rôle.", ephemeral=True
                    )

            else:
                await interaction.followup.send(
                    "Action non prise en charge.", ephemeral=True
                )

        except Exception as e:
            logger.exception(f"Erreur dans roles_execute : {e}")
            await interaction.followup.send(
                "Une erreur est survenue lors du traitement de votre requête.", ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(RolesConfiguration(bot))
    logger.info("RolesConfiguration Cog chargé.")
