import discord
from discord.ext import commands
from cogs.accueil.services.accueil_services import get_welcome_channel_id, get_channel_ids
import logging

logger = logging.getLogger(__name__)

class WelcomeCog(commands.Cog):
    """Cog pour gérer les messages de bienvenue des nouveaux membres."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("WelcomeCog initialisé.")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild_id = member.guild.id
        welcome_channel_id = await get_welcome_channel_id(guild_id)

        if not welcome_channel_id:
            logger.warning(f"Aucun salon d'accueil configuré pour la guilde {guild_id}.")
            return

        welcome_channel = self.bot.get_channel(welcome_channel_id)
        if not welcome_channel:
            logger.error(f"Salon avec l'ID {welcome_channel_id} introuvable dans la guilde {guild_id}.")
            return

        # Récupérer les autres canaux dynamiques (par exemple, règles et présentations)
        actions = ['rules', 'introductions']
        channels = await get_channel_ids(guild_id, actions)
        rules_channel = f"<#{channels['rules']}>" if 'rules' in channels else "le canal des règles"
        introductions_channel = f"<#{channels['introductions']}>" if 'introductions' in channels else "le canal de présentation"

        # Récupérer le pseudo à afficher (display_name utilise le nickname s'il existe)
        username = member.display_name

        # Créer l'embed de bienvenue avec le pseudo affiché en gras par exemple
        embed = discord.Embed(
            title="🎉 Bienvenue sur le serveur ! 🎉",
            description=(
                f"Salut **{username}** ! Nous sommes ravis de t'accueillir parmi nous. 🎉\n\n"
                "Pour bien démarrer, voici quelques informations importantes :\n"
                f"• **Règles du serveur** : Assure-toi de lire {rules_channel}.\n"
                f"• **Découvre le serveur** : Va dans {introductions_channel} pour en apprendre davantage sur notre communauté.\n\n"
            ),
            color=discord.Color.blue()
        )

        # Gérer l'image de l'avatar (avatar moderne et avatar par défaut)
        if member.avatar:
            embed.set_thumbnail(url=member.avatar.url)
        else:
            embed.set_thumbnail(url=member.default_avatar.url)

        embed.set_footer(
            text="N'hésite pas à demander de l'aide si tu as des questions !",
            icon_url=self.bot.user.avatar.url
        )

        try:
            await welcome_channel.send(embed=embed)
            logger.info(f"Message de bienvenue envoyé à {member} dans {welcome_channel.name}.")
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi du message de bienvenue : {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(WelcomeCog(bot))
    logger.info("WelcomeCog chargé.")
