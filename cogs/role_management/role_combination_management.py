# cogs/role_management/role_combination_management.py

import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import List, Dict, Any, Optional

from ..utilities.utils import load_json, save_json

logger = logging.getLogger('discord.role_management.role_combination_management')


class RoleCombinationManagement(commands.Cog):
    """Cog pour gérer l'ajout et la suppression des combinaisons de rôles."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_file = 'data/config.json'
        self.config: Dict[str, Any] = {}
        self.role_combinations: List[Dict[str, Any]] = []
        self.bot.loop.create_task(self.load_config())

    async def load_config(self) -> None:
        """Charge la configuration depuis le fichier JSON."""
        self.config = await load_json(self.config_file)
        self.role_combinations = self.config.get("role_combinations", [])
        logger.info("RoleCombinationManagement: Configuration chargée avec succès.")

    async def save_config(self) -> None:
        """Sauvegarde la configuration dans le fichier JSON."""
        self.config['role_combinations'] = self.role_combinations
        await save_json(self.config_file, self.config)
        logger.info("RoleCombinationManagement: Configuration sauvegardée avec succès.")

    @app_commands.command(name="add_role_combination", description="Ajoute une nouvelle combinaison de rôles.")
    @app_commands.describe(required_roles="Liste des rôles requis, séparés par des virgules", new_role="Nouveau rôle à attribuer")
    @app_commands.checks.has_role("Admin")  # Utiliser le nom du rôle approprié
    async def add_role_combination(
        self,
        interaction: discord.Interaction,
        required_roles: str,
        new_role: str
    ) -> None:
        """
        Ajoute une nouvelle combinaison de rôles à la configuration.

        Parameters:
            interaction (discord.Interaction): L'interaction de l'utilisateur.
            required_roles (str): Rôles requis séparés par des virgules.
            new_role (str): Nouveau rôle à attribuer.
        """
        required_roles_list = [role.strip() for role in required_roles.split(",")]
        self.role_combinations.append({
            'required_roles': required_roles_list,
            'new_role': new_role
        })
        await self.save_config()
        await interaction.response.send_message(
            f"Combinaison de rôles ajoutée: Si un membre a {' et '.join(required_roles_list)}, il recevra le rôle `{new_role}`.",
            ephemeral=True
        )
        logger.info(f"Nouvelle combinaison de rôles ajoutée: {required_roles_list} -> {new_role}")

    @app_commands.command(name="remove_role_combination", description="Supprime une combinaison de rôles existante.")
    @app_commands.describe(new_role="Nouveau rôle à supprimer")
    @app_commands.checks.has_role("Admin")  # Utiliser le nom du rôle approprié
    async def remove_role_combination(
        self,
        interaction: discord.Interaction,
        new_role: str
    ) -> None:
        """
        Supprime une combinaison de rôles de la configuration.

        Parameters:
            interaction (discord.Interaction): L'interaction de l'utilisateur.
            new_role (str): Nouveau rôle à supprimer.
        """
        original_length = len(self.role_combinations)
        self.role_combinations = [
            combo for combo in self.role_combinations if combo.get('new_role') != new_role
        ]
        await self.save_config()
        if len(self.role_combinations) < original_length:
            await interaction.response.send_message(
                f"Combinaison de rôles pour le rôle `{new_role}` supprimée avec succès.",
                ephemeral=True
            )
            logger.info(f"Combinaison de rôles pour le rôle '{new_role}' supprimée.")
        else:
            await interaction.response.send_message(
                f"Aucune combinaison de rôles trouvée pour le rôle `{new_role}`.",
                ephemeral=True
            )
            logger.warning(f"Aucune combinaison de rôles trouvée pour le rôle '{new_role}' à supprimer.")

    @add_role_combination.error
    @remove_role_combination.error
    async def role_combination_error(self, interaction: discord.Interaction, error: Exception) -> None:
        """Gère les erreurs liées aux commandes de gestion des combinaisons de rôles."""
        if isinstance(error, app_commands.MissingRole):
            await interaction.response.send_message(
                "Vous n'avez pas la permission d'utiliser cette commande.",
                ephemeral=True
            )
            logger.warning(f"{interaction.user} a tenté d'utiliser une commande de gestion des rôles sans permissions.")
        else:
            await interaction.response.send_message(
                "Une erreur est survenue lors de l'exécution de la commande.",
                ephemeral=True
            )
            logger.exception(f"Erreur lors de l'exécution de la commande de gestion des rôles par {interaction.user}: {error}")


async def setup(bot: commands.Bot) -> None:
    """Ajoute le Cog RoleCombinationManagement au bot."""
    await bot.add_cog(RoleCombinationManagement(bot))
    logger.info("RoleCombinationManagement Cog chargé avec succès.")
