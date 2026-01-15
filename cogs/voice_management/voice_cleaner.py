import discord
from discord.ext import commands, tasks
import logging
import asyncio
from cogs.configuration.services.channel_service import ServerChannelService

VOICE_CLEANER_CATEGORY_ACTION = "voice_cleaner_category"
VOICE_CLEANER_AFK_ACTION = "voice_cleaner_afk"

logger = logging.getLogger("voice_cleaner")

class VoiceManagement(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Configuration chargee via channel_configurations
        self.check_empty_voice_channels.start()

    def cog_unload(self) -> None:
        self.check_empty_voice_channels.cancel()

    @tasks.loop(minutes=5)
    async def check_empty_voice_channels(self) -> None:
        """
        Verifie toutes les 5 minutes les salons vocaux de la categorie specifiee
        et supprime ceux qui sont vides (sauf le salon AFK).
        """
        try:
            for guild in self.bot.guilds:
                config = await ServerChannelService.get_channels_config(guild.id, guild.name)
                category_id = config.get(VOICE_CLEANER_CATEGORY_ACTION)
                if not category_id:
                    continue

                category = guild.get_channel(category_id)
                if not category:
                    logger.warning(
                        f"Categorie avec l'ID {category_id} introuvable dans la guilde {guild.name}."
                    )
                    continue

                afk_channel_id = config.get(VOICE_CLEANER_AFK_ACTION)

                for channel in category.voice_channels:
                    # Ne pas supprimer le salon AFK
                    if afk_channel_id and channel.id == afk_channel_id:
                        continue
                    if not channel.members:
                        logger.info(
                            f"Suppression du salon vocal vide : {channel.name} dans la guilde {guild.name}."
                        )
                        try:
                            await channel.delete(reason="Salon vocal vide supprime automatiquement.")
                        except Exception as e:
                            logger.error(f"Erreur lors de la suppression du salon {channel.name}: {e}")
        except Exception as e:
            logger.error(f"Erreur lors de la verification des salons vocaux vides : {e}")

    @check_empty_voice_channels.before_loop
    async def before_check_empty_voice_channels(self) -> None:
        """Attend que le bot soit prêt avant de démarrer la tâche."""
        await self.bot.wait_until_ready()
        logger.info("Tâche de vérification des salons vocaux vides démarrée.")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VoiceManagement(bot))
    logger.info("VoiceManagement Cog chargé.")
