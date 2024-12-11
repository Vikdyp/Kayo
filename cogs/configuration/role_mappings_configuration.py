# cogs/configuration/roles_configuration.py

import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Dict

from cogs.utilities.request_manager import enqueue_request
from cogs.utilities.data_manager import DataManager

# Configurer le logger pour ce cog
logger = logging.getLogger('configuration.role')

class RolesConfiguration(commands.Cog):
    """Cog pour gérer la configuration des rôles."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = DataManager()
        self.config: Dict[str, int] = {}
        asyncio.create_task(self.load_config())
        logger.info("RolesConfiguration initialisé.")

    async def load_config(self) -> None:
        """Charge la configuration des rôles depuis la base de données."""
        try:
            full_config = await self.data.get_config()
            self.config = full_config.get("roles", {})
            logger.info("RolesConfiguration: config chargée avec succès.")
        except Exception as e:
            logger.error("RolesConfiguration: Erreur lors du chargement de la config : %s", e)
            self.config = {}

    async def save_config(self) -> None:
        """Sauvegarde la configuration des rôles dans la base de données."""
        try:
            full_config = await self.data.get_config()
            full_config["roles"] = self.config
            await self.data.save_config(full_config)
            logger.info("RolesConfiguration: config sauvegardée avec succès.")
        except Exception as e:
            logger.error("RolesConfiguration: Erreur lors de la sauvegarde de la config : %s", e)

    # Liste prédéfinie des rôles
    PREDEFINED_ROLES = [
        "bon joueur",
        "booster",
        "ban",
        "mauvais joueur",
        "admin",
        "fer",
        "bronze",
        "argent",
        "or",
        "platine",
        "diamant",
        "ascendant",
        "immortel",
        "radiant",
        "sentinel",
        "duelist",
        "controller",
        "initiator",
        "fill"
    ]

    # Création des choix pour les rôles prédéfinis
    ROLE_CHOICES = [
        app_commands.Choice(name=role.capitalize(), value=role)
        for role in PREDEFINED_ROLES
    ]

    # Groupe de commandes /role
    role_group = app_commands.Group(
        name="role",
        description="Gérer la configuration des rôles",
        default_permissions=discord.Permissions(administrator=True)  # Restriction aux administrateurs
    )

    @role_group.command(name="get", description="Affiche les rôles configurés.")
    @enqueue_request()
    async def roles_get(self, interaction: discord.Interaction):
        """Commande /role get : Affiche les rôles configurés."""
        try:
            logger.debug(f"Executing roles_get pour interaction={interaction.id}")
            if not interaction.guild:
                await interaction.followup.send(
                    "Cette commande doit être exécutée dans un serveur.", ephemeral=True
                )
                return

            roles = self.config
            logger.debug(f"Roles config: {roles}")
            if not roles:
                await interaction.followup.send("Aucun rôle configuré.", ephemeral=True)
                return

            embed = discord.Embed(title="Rôles Configurés", color=discord.Color.blue())
            for role_key, role_id in roles.items():
                role = interaction.guild.get_role(role_id)
                if role:
                    embed.add_field(name=self.get_role_display_name(role_key), value=role.name, inline=False)
                else:
                    embed.add_field(name=self.get_role_display_name(role_key), value="Rôle non trouvé", inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.debug(f"roles_get exécuté avec succès pour interaction={interaction.id}")
        except Exception as e:
            logger.exception(f"Erreur dans roles_get pour interaction={interaction.id}: {e}")
            await interaction.followup.send(
                "Une erreur est survenue lors du traitement de votre requête.", ephemeral=True
            )

    @role_group.command(name="set", description="Configure un rôle pour une action spécifique.")
    @app_commands.describe(role_name="Nom du rôle", role="Rôle Discord")
    @app_commands.choices(role_name=ROLE_CHOICES)
    @enqueue_request()
    async def roles_set(self, interaction: discord.Interaction, role_name: app_commands.Choice[str], role: discord.Role):
        """Commande /role set : Configure un rôle pour une action spécifique."""
        try:
            logger.debug(f"Executing roles_set pour interaction={interaction.id} avec role_name={role_name.value}, role={role.id}")
            if not interaction.guild:
                await interaction.followup.send(
                    "Cette commande doit être exécutée dans un serveur.", ephemeral=True
                )
                return

            if role.guild.id != interaction.guild.id:
                await interaction.followup.send(
                    "Le rôle doit appartenir à ce serveur.", ephemeral=True
                )
                return

            role_name_lower = role_name.value.lower()
            if role_name_lower not in [r.lower() for r in self.PREDEFINED_ROLES]:
                await interaction.followup.send(
                    f"Rôle invalide. Choisissez parmi les suivantes : {', '.join(self.PREDEFINED_ROLES)}.", ephemeral=True
                )
                return

            self.config[role_name_lower] = role.id
            await self.save_config()
            await interaction.followup.send(
                f"Rôle {role.name} configuré pour {self.get_role_display_name(role_name_lower)}.", ephemeral=True
            )
            logger.debug(f"roles_set exécuté avec succès pour interaction={interaction.id}")
        except Exception as e:
            logger.exception(f"Erreur dans roles_set pour interaction={interaction.id}: {e}")
            await interaction.followup.send(
                "Une erreur est survenue lors du traitement de votre requête.", ephemeral=True
            )

    @role_group.command(name="remove", description="Supprime la configuration d'un rôle pour une action.")
    @app_commands.describe(role_name="Nom du rôle")
    @app_commands.choices(role_name=ROLE_CHOICES)
    @enqueue_request()
    async def roles_remove(self, interaction: discord.Interaction, role_name: app_commands.Choice[str]):
        """Commande /role remove : Supprime la configuration d'un rôle pour une action."""
        try:
            logger.debug(f"Executing roles_remove pour interaction={interaction.id} avec role_name={role_name.value}")
            if not interaction.guild:
                await interaction.followup.send(
                    "Cette commande doit être exécutée dans un serveur.", ephemeral=True
                )
                return

            role_name_lower = role_name.value.lower()
            if role_name_lower not in self.config:
                await interaction.followup.send(
                    f"Aucune configuration trouvée pour le rôle {self.get_role_display_name(role_name_lower)}.", ephemeral=True
                )
                logger.warning(f"{interaction.user} a tenté de supprimer un mapping inexistant: {role_name.value}")
                return

            del self.config[role_name_lower]
            await self.save_config()
            await interaction.followup.send(
                f"Configuration pour le rôle {self.get_role_display_name(role_name_lower)} supprimée.", ephemeral=True
            )
            logger.debug(f"roles_remove exécuté avec succès pour interaction={interaction.id}")
        except Exception as e:
            logger.exception(f"Erreur dans roles_remove pour interaction={interaction.id}: {e}")
            await interaction.followup.send(
                "Une erreur est survenue lors du traitement de votre requête.", ephemeral=True
            )

    def get_role_display_name(self, role_key: str) -> str:
        """Retourne le nom affiché du rôle."""
        return role_key.capitalize()

async def setup(bot: commands.Bot):
    await bot.add_cog(RolesConfiguration(bot))
    logger.info("RolesConfiguration Cog chargé.")
