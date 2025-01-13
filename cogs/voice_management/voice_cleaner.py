# cogs\voice_management\voice_cleaner.py

import discord
from discord.ext import commands, tasks
import logging
import asyncio
import time

logger = logging.getLogger("voice_cleaner")

class VoiceManagement(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.category_id = 1323077627413794847  # ID de la catégorie à surveiller
        self.afk_channel_id = 123456789012345678  # Remplacez par l'ID de votre salon AFK
        self.inactivity_threshold = 300  # 10 minutes en secondes
        self.last_active = {}  # Dictionnaire pour stocker les timestamps d'activité des membres

        self.check_empty_voice_channels.start()

    def cog_unload(self):
        self.check_empty_voice_channels.cancel()

    @tasks.loop(minutes=5)  # Intervalle de vérification toutes les 5 minutes
    async def check_empty_voice_channels(self):
        try:
            for guild in self.bot.guilds:
                category = guild.get_channel(self.category_id)
                if not category:
                    logger.warning(f"Catégorie avec l'ID {self.category_id} non trouvée dans la guilde {guild.name}.")
                    continue

                voice_channels = category.voice_channels
                for channel in voice_channels:
                    if len(channel.members) == 0:
                        logger.info(f"Suppression du salon vocal vide : {channel.name} dans la guilde {guild.name}.")
                        await channel.delete(reason="Salon vocal vide supprimé automatiquement.")
        except Exception as e:
            logger.error(f"Erreur lors de la vérification des salons vocaux vides : {e}")

    @check_empty_voice_channels.before_loop
    async def before_check_empty_voice_channels(self):
        await self.bot.wait_until_ready()
        logger.info("Tâche de vérification des salons vocaux vides démarrée.")

async def setup(bot):
    await bot.add_cog(VoiceManagement(bot))
    logger.info("VoiceManagement Cog chargé.")
