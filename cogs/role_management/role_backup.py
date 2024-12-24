# cogs/role_management/role_backup.py

import discord
from discord.ext import commands
import logging
from typing import List, Dict

from cogs.utilities.data_manager import DataManager

logger = logging.getLogger('discord.role_management.role_backup')

class RoleBackup(commands.Cog):
    """Cog pour sauvegarder et restaurer les rôles des membres."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = DataManager()
        self.role_backup: Dict[str, List[int]] = {}
        self.bot.loop.create_task(self.load_role_backup())

    async def load_role_backup(self) -> None:
        """Charge les sauvegardes de rôles depuis le fichier JSON."""
        self.role_backup = await self.data.get_role_backup()
        logger.info("RoleBackup: Sauvegardes de rôles chargées avec succès.")

    async def save_role_backup(self) -> None:
        """Sauvegarde les données de rôles dans le fichier JSON."""
        await self.data.save_role_backup(self.role_backup)
        logger.info("RoleBackup: Sauvegardes de rôles sauvegardées avec succès.")

    async def backup_roles(self, member: discord.Member) -> None:
        """
        Sauvegarde les rôles actuels d'un membre (excluant le rôle par défaut et le rôle 'ban').

        Args:
            member (discord.Member): Le membre dont les rôles sont à sauvegarder.
        """
        # Exclure le rôle par défaut et le rôle 'ban'
        roles_to_backup = [
            role.id for role in member.roles 
            if role != member.guild.default_role and role.name.lower() != "ban"
        ]

        if roles_to_backup:
            self.role_backup[str(member.id)] = roles_to_backup
            await self.save_role_backup()
            logger.info(f"Rôles de {member.display_name} sauvegardés: {roles_to_backup}")
        else:
            logger.warning(f"Aucun rôle à sauvegarder pour {member.display_name}.")

    async def restore_roles(self, member: discord.Member) -> None:
        """
        Restaure les rôles sauvegardés d'un membre.

        Args:
            member (discord.Member): Le membre dont les rôles sont à restaurer.
        """
        roles = self.role_backup.get(str(member.id), [])

        if not roles:
            logger.warning(f"Aucune sauvegarde de rôles trouvée pour {member.display_name}.")
            return

        # Récupérer les objets Role existants dans le serveur
        roles_to_add = [
            discord.utils.get(member.guild.roles, id=role_id) 
            for role_id in roles
        ]
        roles_to_add = [role for role in roles_to_add if role is not None]

        if roles_to_add:
            try:
                await member.add_roles(*roles_to_add, reason="Restauration des rôles après débannissement.")
                logger.info(f"Rôles restaurés pour {member.display_name}: {[role.name for role in roles_to_add]}")
            except discord.Forbidden:
                logger.error(f"Permission refusée pour restaurer les rôles de {member.display_name}.")
            except discord.HTTPException as e:
                logger.exception(f"Erreur lors de la restauration des rôles de {member.display_name}: {e}")
        else:
            logger.warning(f"Aucun rôle valide à restaurer pour {member.display_name}.")

        # Supprimer les données de sauvegarde après restauration pour libérer de l'espace
        self.role_backup.pop(str(member.id), None)
        await self.save_role_backup()
        logger.debug(f"Données de rôles supprimées pour {member.display_name} après restauration.")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """
        Écoute l'événement lorsque un membre quitte ou est banni du serveur.
        Si le membre est banni, sauvegarde ses rôles.
        """
        guild = member.guild
        # Vérifiez si le membre est banni
        bans = await guild.bans()
        for ban in bans:
            if ban.user.id == member.id:
                await self.backup_roles(member)
                break

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """
        Écoute l'événement lorsqu'un membre rejoint le serveur.
        Restaure ses rôles s'il a été précédemment banni.
        """
        await self.restore_roles(member)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RoleBackup(bot))
    logger.info("RoleBackup Cog chargé avec succès.")
