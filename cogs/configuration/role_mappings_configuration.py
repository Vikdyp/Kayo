# cogs\configuration\role_mappings_configuration.py
import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Optional, List

from utils.request_manager import enqueue_request
from cogs.configuration.services.role_service import RoleService

logger = logging.getLogger('roles_configuration')

class RolesConfiguration(commands.Cog):
    """Cog pour gérer la configuration des rôles."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("RolesConfiguration initialisé.")

    # Liste plate des rôles prédefinis
    PREDEFINED_ROLES = [
        "bon joueur", "booster", "ban", "mauvais joueur", "admin",
        "fer", "bronze", "argent", "or", "platine", "diamant", "ascendant",
        "immortel", "radiant", "sentinel", "duelist", "controller", "initiator", "fill",
        "valorant", "valorant e-sports", "valorant tryhard", "valorant chill",
        "rocket league", "rocket league tryhard", "rocket league chill",
        "tryhard", "e-sports", "chill"
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
        ]
        # Notez que nous avons retiré les choix pour role_name ici
    )
    @enqueue_request()
    async def roles_execute(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        role_name: Optional[str] = None,  # Utilisation de str au lieu de Choice[str]
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

                # Préparer le message en texte brut avec mentions de rôles
                role_list = "**Rôles Configurés:**\n"
                for role_key, role_id in roles.items():
                    guild_role = interaction.guild.get_role(role_id)
                    if guild_role:
                        role_mention = guild_role.mention
                    else:
                        role_mention = "Rôle non trouvé"
                    role_list += f"• **{role_key.capitalize()}**: {role_mention}\n"

                    # Vérifier si la longueur dépasse 1900 caractères (pour éviter de dépasser 2000)
                    if len(role_list) > 1900:
                        await interaction.followup.send(role_list, ephemeral=True)
                        role_list = ""

                # Envoyer le reste des rôles
                if role_list:
                    await interaction.followup.send(role_list, ephemeral=True)

            elif action.value == "set":
                if not role_name or not role:
                    await interaction.followup.send(
                        "Veuillez spécifier un rôle (role_name) et un rôle Discord (role).", ephemeral=True
                    )
                    return

                success = await RoleService.set_role_for_action(
                    interaction.guild.id, role_name, role.id
                )
                if success:
                    await interaction.followup.send(
                        f"Rôle **{role.name}** configuré pour **{role_name.capitalize()}**.", ephemeral=True
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
                    interaction.guild.id, role_name
                )
                if success:
                    await interaction.followup.send(
                        f"Configuration pour **{role_name.capitalize()}** supprimée.", ephemeral=True
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

    @roles_execute.autocomplete('role_name')
    async def role_name_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        """Fournit une liste d'auto-complétion pour les noms de rôles non configurés."""
        try:
            # Récupérer les rôles déjà configurés
            configured_roles = await RoleService.get_roles_config(interaction.guild.id)
            configured_role_keys = set(configured_roles.keys()) if configured_roles else set()

            # Générer les rôles non configurés
            available_roles = [
                role
                for role in self.PREDEFINED_ROLES
                if role not in configured_role_keys
                and (current.lower() in role.lower())
            ]

            # Générer les choix d'autocomplétion avec les rôles disponibles
            choices = [
                app_commands.Choice(name=role.capitalize(), value=role)
                for role in available_roles
                if current.lower() in role.lower()
            ]

            # Limiter à 25 choix
            return choices[:25]
        except Exception as e:
            logger.exception(f"Erreur dans l'autocomplétion de role_name : {e}")
            return []

async def setup(bot: commands.Bot):
    await bot.add_cog(RolesConfiguration(bot))
    logger.info("RolesConfiguration Cog chargé.")
