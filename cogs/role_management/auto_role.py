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
        Vérifie si l'utilisateur est banni globalement et lui applique le rôle 'ban' si c'est le cas.
        """
        guild = member.guild

        # Vérifier si l'utilisateur est banni globalement
        ban_info = await ModerationService.get_ban_info(member.id)
        if ban_info:
            # Récupérer le rôle ban du serveur
            ban_role_id = await ModerationService.get_ban_role_id(guild.id)
            if ban_role_id:
                ban_role = guild.get_role(ban_role_id)
                if ban_role:
                    try:
                        await member.add_roles(ban_role, reason="Ban global appliqué automatiquement")
                        logger.info(f"Rôle 'ban' appliqué à {member} (ID: {member.id}) - ban global")
                    except discord.Forbidden:
                        logger.error(f"Permission refusée pour attribuer le rôle 'ban' à {member}.")
                    except discord.HTTPException as e:
                        logger.error(f"Erreur HTTP lors de l'attribution du rôle 'ban' à {member}: {e}")
                else:
                    logger.warning(f"Rôle 'ban' avec ID {ban_role_id} introuvable dans le serveur '{guild.name}'.")
            else:
                logger.warning(f"Aucun rôle 'ban' configuré pour le serveur '{guild.name}' (ID: {guild.id}).")

async def setup(bot: commands.Bot):
    await bot.add_cog(AutoRoleAssign(bot))
    logger.info("AutoRoleAssign Cog chargé avec succès.")
