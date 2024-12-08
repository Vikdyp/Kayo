# cogs/role_management/role_assignment.py

import discord
from discord.ext import commands
import logging
from typing import List, Dict, Any, Optional

from ..utilities.utils import load_json, save_json

logger = logging.getLogger('discord.role_management.role_assignment')


class RoleAssignment(commands.Cog):
    """Cog pour attribuer et supprimer des rôles basés sur les combinaisons de rôles des membres."""

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
        logger.info("RoleAssignment: Configuration chargée avec succès.")

    async def save_config(self) -> None:
        """Sauvegarde la configuration dans le fichier JSON."""
        self.config['role_combinations'] = self.role_combinations
        await save_json(self.config_file, self.config)
        logger.info("RoleAssignment: Configuration sauvegardée avec succès.")

    async def check_roles(self, member: discord.Member) -> None:
        """
        Vérifie les rôles d'un membre et attribue/supprime les rôles en conséquence.

        Parameters:
            member (discord.Member): Le membre à vérifier.
        """
        roles_to_remove = set()
        roles_to_add = set()

        for combination in self.role_combinations:
            required_roles = combination.get('required_roles', [])
            new_role_name = combination.get('new_role')

            # Récupérer les objets de rôle requis
            required_role_objects = [discord.utils.get(member.guild.roles, name=role) for role in required_roles]
            new_role = discord.utils.get(member.guild.roles, name=new_role_name)

            # Vérifier si tous les rôles requis sont présents
            if all(role in member.roles for role in required_role_objects if role is not None) and new_role:
                if new_role not in member.roles:
                    roles_to_add.add(new_role)
                    logger.info(f"Attribution du rôle '{new_role.name}' à {member.display_name}.")

                # Ajouter les rôles requis à la liste des rôles à retirer
                for role in required_role_objects:
                    if role and role in member.roles:
                        roles_to_remove.add(role)

        # Appliquer les rôles à ajouter
        if roles_to_add:
            try:
                await member.add_roles(*roles_to_add, reason="Gestion automatique des rôles.")
                logger.info(f"{member.display_name} a reçu les rôles: {[role.name for role in roles_to_add]}")
            except discord.Forbidden:
                logger.error(f"Permission refusée pour ajouter des rôles à {member.display_name}.")
            except Exception as e:
                logger.exception(f"Erreur lors de l'ajout des rôles à {member.display_name}: {e}")

        # Appliquer les rôles à retirer
        if roles_to_remove:
            try:
                await member.remove_roles(*roles_to_remove, reason="Gestion automatique des rôles.")
                logger.info(f"{member.display_name} a perdu les rôles: {[role.name for role in roles_to_remove]}")
            except discord.Forbidden:
                logger.error(f"Permission refusée pour retirer des rôles à {member.display_name}.")
            except Exception as e:
                logger.exception(f"Erreur lors de la suppression des rôles à {member.display_name}: {e}")

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        """
        Listener pour l'événement on_member_update.

        Parameters:
            before (discord.Member): L'état du membre avant la mise à jour.
            after (discord.Member): L'état du membre après la mise à jour.
        """
        # Vérifier si les rôles ont changé
        if before.roles != after.roles:
            await self.check_roles(after)


async def setup(bot: commands.Bot) -> None:
    """Ajoute le Cog RoleAssignment au bot."""
    await bot.add_cog(RoleAssignment(bot))
    logger.info("RoleAssignment Cog chargé avec succès.")
