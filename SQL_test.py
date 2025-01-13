import discord
from discord.ext import commands
import logging
from cogs.voice_management.services.five_stack_service import MatchmakingService
from utils.database import database
from typing import Optional, Dict

logger = logging.getLogger(__name__)

class TestUserInfoCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="get_user_info", help="Récupère les informations Valorant d'un utilisateur Discord.")
    async def get_user_info_command(self, ctx: commands.Context, member: discord.Member):
        """
        Commande pour récupérer et afficher les informations Valorant d'un utilisateur.

        Args:
            ctx (commands.Context): Le contexte de la commande.
            member (discord.Member): L'utilisateur Discord à tester.
        """
        discord_id = member.id
        logger.info(f"Commande reçue pour récupérer les informations de {member.display_name} (ID: {discord_id}).")

        # Étape 1 : Connexion à la base de données
        await database.connect()

        try:
            # Étape 2 : Récupérer les informations utilisateur
            user_info = await MatchmakingService.get_user_info(discord_id)
            
            if user_info:
                elo = user_info.get("elo", "Non défini")
                region = user_info.get("region", "Non défini")
                response = (
                    f"**Informations Valorant de {member.mention} :**\n"
                    f"**Région** : {region}\n"
                    f"**MMR (Elo)** : {elo}"
                )
                await ctx.send(response)
                logger.info(f"Informations récupérées pour {member.display_name}: Région={region}, Elo={elo}.")
            else:
                await ctx.send(f"Aucune information Valorant trouvée pour {member.mention}.")
                logger.warning(f"Aucune information Valorant trouvée pour Discord ID {discord_id}.")

        except Exception as e:
            logger.error(f"Erreur lors de la récupération des informations utilisateur : {e}")
            await ctx.send("Une erreur s'est produite lors de la récupération des informations utilisateur.")
        finally:
            # Étape 3 : Déconnexion de la base de données
            await database.disconnect()

    @staticmethod
    async def get_user_info(discord_id: int) -> Optional[Dict]:
        """
        Récupère les informations Valorant d'un utilisateur à partir de la base de données.

        Args:
            discord_id (int): L'ID Discord de l'utilisateur.

        Returns:
            Optional[Dict]: Un dictionnaire contenant 'elo' et 'region' si trouvé, sinon None.
        """
        query = """
        SELECT valorant_elo, valorant_region
        FROM user_id
        WHERE discord_id = $1;
        """
        try:
            row = await database.fetchrow(query, discord_id)
            if row:
                logger.debug(f"Informations récupérées pour Discord ID {discord_id}: {row}")
                return {
                    "elo": row["valorant_elo"],
                    "region": row["valorant_region"]
                }
            logger.warning(f"Informations Valorant non trouvées pour Discord ID {discord_id}.")
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des informations utilisateur : {e}")
        return None

async def setup(bot: commands.Bot):
    await bot.add_cog(TestUserInfoCog(bot))
    logger.info("TestUserInfoCog chargé.")
