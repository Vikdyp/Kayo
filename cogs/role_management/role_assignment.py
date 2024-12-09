# cogs/role_management/role_assignment.py

import discord
from discord.ext import commands
import logging
from typing import List, Dict, Any

from cogs.utilities.data_manager import DataManager

logger = logging.getLogger('discord.role_management.role_assignment')

class RoleAssignment(commands.Cog):
    """Cog pour attribuer et supprimer des rôles basés sur les combinaisons de rôles des membres."""

    dependencies = []

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = DataManager()
        self.config: Dict[str, Any] = {}
        self.role_combinations: List[Dict[str, Any]] = []
        self.bot.loop.create_task(self.load_config())

    async def load_config(self) -> None:
        """Charge la configuration depuis le DataManager."""
        self.config = await self.data.get_config()
        self.role_combinations = self.config.get("role_combinations", [])
        logger.info("RoleAssignment: Configuration chargée avec succès.")

    async def save_config(self) -> None:
        """Sauvegarde la configuration dans le DataManager."""
        self.config['role_combinations'] = self.role_combinations
        await self.data.save_config(self.config)
        logger.info("RoleAssignment: Configuration sauvegardée avec succès.")

    async def check_roles(self, member: discord.Member) -> None:
        roles_to_remove = set()
        roles_to_add = set()

        for combination in self.role_combinations:
            required_roles = combination.get('required_roles', [])
            new_role_name = combination.get('new_role')

            required_role_objects = [discord.utils.get(member.guild.roles, name=role) for role in required_roles]
            new_role = discord.utils.get(member.guild.roles, name=new_role_name)

            if all(role in member.roles for role in required_role_objects if role is not None) and new_role:
                if new_role not in member.roles:
                    roles_to_add.add(new_role)
                    logger.info(f"Attribution du rôle '{new_role.name}' à {member.display_name}.")

                for role in required_role_objects:
                    if role and role in member.roles:
                        roles_to_remove.add(role)

        if roles_to_add:
            try:
                await member.add_roles(*roles_to_add, reason="Gestion automatique des rôles.")
                logger.info(f"{member.display_name} a reçu les rôles: {[role.name for role in roles_to_add]}")
            except discord.Forbidden:
                logger.error(f"Permission refusée pour ajouter des rôles à {member.display_name}.")
            except Exception as e:
                logger.exception(f"Erreur lors de l'ajout des rôles à {member.display_name}: {e}")

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
        if before.roles != after.roles:
            await self.check_roles(after)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RoleAssignment(bot))
    logger.info("RoleAssignment Cog chargé avec succès.")
