# cogs\role_management\auto_role.py

import discord
from discord.ext import commands
import logging

from cogs.role_management.services.auto_role_service import AutoRoleService

logger = logging.getLogger('auto_role_assign')

class AutoRoleAssign(commands.Cog):
    """Cog pour attribuer automatiquement le rôle 'tester' aux nouveaux membres."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("AutoRoleAssign Cog initialisé.")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """
        Événement déclenché lorsqu'un nouveau membre rejoint le serveur.
        Attribue le rôle 'tester' si configuré.
        """
        guild = member.guild
        guild_id = guild.id
        role_name = "tester"

        logger.info(f"Nouveau membre rejoint: {member} (ID: {member.id}) dans le serveur '{guild.name}' (ID: {guild_id})")

        # Récupérer l'ID du rôle 'tester' via le service
        role_id = await AutoRoleService.get_tester_role_id(guild_id)

        if not role_id:
            logger.warning(f"Rôle '{role_name}' non configuré pour le serveur '{guild.name}' (ID: {guild_id}).")
            return

        role = guild.get_role(role_id)
        if not role:
            logger.error(f"Rôle avec ID {role_id} introuvable dans le serveur '{guild.name}' (ID: {guild_id}).")
            return

        try:
            await member.add_roles(role, reason="Attribution automatique du rôle 'tester' lors de la jonction.")
            logger.info(f"Rôle '{role.name}' attribué à {member}.")
        except discord.Forbidden:
            logger.error(f"Permission refusée pour attribuer le rôle '{role.name}' à {member}.")
        except discord.HTTPException as e:
            logger.error(f"Erreur HTTP lors de l'attribution du rôle '{role.name}' à {member}: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(AutoRoleAssign(bot))
    logger.info("AutoRoleAssign Cog chargé avec succès.")
