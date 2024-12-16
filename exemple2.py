# cogs/user_cog.py

from discord.ext import commands
from discord import Interaction
from cogs.utilities.confirmation_view import ConfirmationView
from services.user_service import UserService
import discord
import logging

logger = logging.getLogger('discord.cogs.user_cog')

class UserCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def deleteuser(self, ctx, member: discord.Member):
        """Supprime un utilisateur de la base de données. Réservé aux administrateurs."""
        
        async def confirmation_callback(result: Optional[bool]):
            if result is True:
                success = await UserService.delete_user(member.id)
                if success:
                    await ctx.send(f"{member.display_name} a été supprimé de la base de données.")
                else:
                    await ctx.send("Une erreur est survenue lors de la suppression de l'utilisateur.")
            elif result is False:
                await ctx.send("Suppression de l'utilisateur annulée.")
            else:
                await ctx.send("Le délai de confirmation a expiré.")

        view = ConfirmationView(
            interaction=ctx.interaction if hasattr(ctx, 'interaction') else ctx,
            callback=confirmation_callback
        )
        await ctx.send(f"Êtes-vous sûr de vouloir supprimer {member.display_name} de la base de données ?", view=view)

    @deleteuser.error
    async def deleteuser_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("Vous n'avez pas les permissions nécessaires pour utiliser cette commande.")
        else:
            logger.error(f"Erreur dans la commande deleteuser: {error}")
            await ctx.send("Une erreur est survenue lors de l'exécution de la commande.")

def setup(bot):
    bot.add_cog(UserCog(bot))
