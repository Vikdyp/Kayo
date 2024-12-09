# cogs/role_management/role_backup.py

import discord
from discord.ext import commands
import logging
from typing import List, Dict

from cogs.utilities.data_manager import DataManager

logger = logging.getLogger('discord.role_management.role_backup')

class RoleBackup(commands.Cog):
    """Cog pour sauvegarder et restaurer les rôles des membres."""

    dependencies = []

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = DataManager()
        self.role_backup: Dict[str, List[int]] = {}
        self.bot.loop.create_task(self.load_role_backup())

    async def load_role_backup(self) -> None:
        self.role_backup = await self.data.get_role_backup()
        logger.info("RoleBackup: Sauvegardes de rôles chargées avec succès.")

    async def save_role_backup(self) -> None:
        await self.data.save_role_backup(self.role_backup)
        logger.info("RoleBackup: Sauvegardes de rôles sauvegardées avec succès.")

    async def backup_roles(self, member: discord.Member) -> None:
        self.role_backup[str(member.id)] = [role.id for role in member.roles if role != member.guild.default_role]
        await self.save_role_backup()
        logger.info(f"Rôles de {member.display_name} sauvegardés.")

    async def restore_roles(self, member: discord.Member) -> None:
        roles = self.role_backup.get(str(member.id), [])
        roles_to_add = [discord.utils.get(member.guild.roles, id=role_id) for role_id in roles]
        roles_to_add = [role for role in roles_to_add if role is not None]
        if roles_to_add:
            try:
                await member.add_roles(*roles_to_add, reason="Restauration des rôles après bannissement.")
                logger.info(f"Rôles restaurés pour {member.display_name}.")
            except discord.Forbidden:
                logger.error(f"Permission refusée pour restaurer les rôles de {member.display_name}.")
            except Exception as e:
                logger.exception(f"Erreur lors de la restauration des rôles de {member.display_name}: {e}")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RoleBackup(bot))
    logger.info("RoleBackup Cog chargé avec succès.")
