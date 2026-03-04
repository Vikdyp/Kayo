# cogs/role_management/auto_role.py
"""
Cog pour appliquer automatiquement le rôle 'ban' aux membres bannis - UI Discord uniquement.
"""

import discord
from discord.ext import commands
import logging

from cogs.moderation.services.moderation_service import ModerationService

logger = logging.getLogger(__name__)


class AutoRoleAssign(commands.Cog):
    """Applique automatiquement le rôle 'ban' aux membres bannis lors du join."""

    def __init__(self, bot: commands.Bot, moderation_service: ModerationService):
        self.bot = bot
        self._mod_svc = moderation_service
        logger.info("AutoRoleAssign initialisé.")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Vérifie si le membre est banni et applique le rôle 'ban'."""
        guild = member.guild

        ban_info = await self._mod_svc.get_ban_info(guild.id, member.id)
        if not ban_info:
            return

        ban_role_id = await self._mod_svc.get_ban_role_id(guild.id)
        if not ban_role_id:
            logger.warning(f"Aucun rôle 'ban' configuré pour guild {guild.id}.")
            return

        ban_role = guild.get_role(ban_role_id)
        if not ban_role:
            logger.warning(f"Rôle 'ban' (id={ban_role_id}) introuvable dans guild {guild.id}.")
            return

        try:
            await member.add_roles(ban_role, reason="Ban global appliqué automatiquement")
            logger.info(f"Rôle 'ban' appliqué à {member} (ID: {member.id})")
        except discord.Forbidden:
            logger.error(f"Permission refusée pour attribuer le rôle 'ban' à {member}.")
        except discord.HTTPException as e:
            logger.error(f"Erreur HTTP attribution rôle 'ban' à {member}: {e}")


async def setup(bot: commands.Bot):
    moderation_service = getattr(bot, "moderation_service", None)
    if moderation_service is None:
        logger.error("moderation_service non initialisé. AutoRoleAssign non chargé.")
        return
    await bot.add_cog(AutoRoleAssign(bot, moderation_service))
    logger.info("AutoRoleAssign chargé.")
