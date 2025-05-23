import discord
from discord.ext import commands, tasks
import logging
import asyncio

logger = logging.getLogger("voice_cleaner")

class VoiceManagement(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # ID de la catégorie à surveiller pour la suppression des salons vocaux vides
        self.category_id: int = 1323077627413794847
        # ID du salon AFK à exclure de la suppression
        self.afk_channel_id: int = 123456789012345678
        # Démarrage de la tâche de vérification des salons vocaux vides
        self.check_empty_voice_channels.start()

    def cog_unload(self) -> None:
        self.check_empty_voice_channels.cancel()

    @tasks.loop(minutes=5)
    async def check_empty_voice_channels(self) -> None:
        """
        Vérifie toutes les 5 minutes les salons vocaux de la catégorie spécifiée
        et supprime ceux qui sont vides (sauf le salon AFK).
        """
        try:
            for guild in self.bot.guilds:
                category = guild.get_channel(self.category_id)
                if not category:
                    logger.warning(f"Catégorie avec l'ID {self.category_id} non trouvée dans la guilde {guild.name}.")
                    continue

                for channel in category.voice_channels:
                    # Ne pas supprimer le salon AFK
                    if channel.id == self.afk_channel_id:
                        continue
                    if not channel.members:
                        logger.info(f"Suppression du salon vocal vide : {channel.name} dans la guilde {guild.name}.")
                        try:
                            await channel.delete(reason="Salon vocal vide supprimé automatiquement.")
                        except Exception as e:
                            logger.error(f"Erreur lors de la suppression du salon {channel.name}: {e}")
        except Exception as e:
            logger.error(f"Erreur lors de la vérification des salons vocaux vides : {e}")

    @check_empty_voice_channels.before_loop
    async def before_check_empty_voice_channels(self) -> None:
        """Attend que le bot soit prêt avant de démarrer la tâche."""
        await self.bot.wait_until_ready()
        logger.info("Tâche de vérification des salons vocaux vides démarrée.")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VoiceManagement(bot))
    logger.info("VoiceManagement Cog chargé.")
