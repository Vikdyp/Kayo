# cogs\role_management\auto_role.py

import discord
from discord.ext import commands
import logging

from cogs.moderation.services.moderation_service import ModerationService

logger = logging.getLogger('auto_role_assign')

class AutoRoleAssign(commands.Cog):
    """Cog pour appliquer automatiquement le rôle 'ban' aux membres bannis globalement."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("AutoRoleAssign Cog initialisé.")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """
        Événement déclenché lorsqu'un nouveau membre rejoint le serveur.
        Note: La gestion du re-ban est maintenant faite dans le cog Moderation
        qui attend la fin de l'onboarding avant d'appliquer le rôle ban.
        Ce listener est conservé pour compatibilité mais ne fait plus rien.
        """
        # La logique de re-ban est maintenant gérée par Moderation.on_member_join
        # et Moderation.on_member_update pour attendre la fin de l'onboarding
        pass

async def setup(bot: commands.Bot):
    await bot.add_cog(AutoRoleAssign(bot))
    logger.info("AutoRoleAssign Cog chargé avec succès.")
