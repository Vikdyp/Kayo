import discord
from discord.ext import commands, tasks
import logging
import asyncio
from typing import Dict

from cogs.configuration.services.channel_service import ServerChannelService

logger = logging.getLogger("voice_cleaner")

class VoiceManagement(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # ID de la catégorie à surveiller par guilde
        self.category_ids: Dict[int, int] = {}
        # ID du salon AFK par guilde
        self.afk_channel_ids: Dict[int, int] = {}
        # Démarrage de la tâche de vérification des salons vocaux vides
        self.check_empty_voice_channels.start()

    def cog_unload(self) -> None:
        self.check_empty_voice_channels.cancel()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        for guild in self.bot.guilds:
            cat = await ServerChannelService.get_channel_for_action(guild.id, guild.name, "temp_vocal_category")
            if cat:
                self.category_ids[guild.id] = cat
            afk = await ServerChannelService.get_channel_for_action(guild.id, guild.name, "afk_channel")
            if afk:
                self.afk_channel_ids[guild.id] = afk

    @tasks.loop(minutes=5)
    async def check_empty_voice_channels(self) -> None:
        """
        Vérifie toutes les 5 minutes les salons vocaux de la catégorie spécifiée
        et supprime ceux qui sont vides (sauf le salon AFK).
        """
        try:
            for guild in self.bot.guilds:
                category_id = self.category_ids.get(guild.id)
                if not category_id:
                    continue
                category = guild.get_channel(category_id)
                if not category:
                    continue

                afk_id = self.afk_channel_ids.get(guild.id)
                for channel in category.voice_channels:
                    if afk_id and channel.id == afk_id:
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
