# cogs/voice_management/cleanup.py

import discord
from discord.ext import commands, tasks
from datetime import datetime, timezone, timedelta
import logging
from typing import Dict, Any, Optional

from cogs.utilities.utils import load_json, save_json

logger = logging.getLogger('discord.voice_management.cleanup')

class VoiceChannelCleanup(commands.Cog):
    """Cog pour gérer le nettoyage des salons vocaux inactifs."""

    dependencies = []

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_file = 'data/config.json'
        self.config: Dict[str, Any] = {}
        self.tracked_channels: Dict[int, Dict[str, Any]] = {}
        self.bot.loop.create_task(self.load_config())
        self.check_empty_channels.start()

    async def load_config(self) -> None:
        """Charge la configuration depuis le fichier JSON."""
        self.config = await load_json(self.config_file)
        logger.info("VoiceChannelCleanup: Configuration chargée avec succès.")

    async def save_config(self) -> None:
        """Sauvegarde la configuration dans le fichier JSON."""
        await save_json(self.config, self.config_file)
        logger.info("VoiceChannelCleanup: Configuration sauvegardée avec succès.")

    @tasks.loop(seconds=30)
    async def check_empty_channels(self):
        """Vérifie régulièrement l'état des salons vocaux suivis et les supprime s'ils sont inactifs."""
        for channel_id, info in list(self.tracked_channels.items()):
            voice_channel: discord.VoiceChannel = info["voice_channel"]
            if len(voice_channel.members) == 0:
                time_since_last_active = datetime.now(timezone.utc) - info["last_active"]
                if time_since_last_active > timedelta(minutes=2):
                    try:
                        await voice_channel.delete()
                        if info.get("invite_message"):
                            try:
                                await info["invite_message"].delete()
                            except discord.HTTPException:
                                logger.warning(f"Impossible de supprimer l'invitation liée au salon {voice_channel.name}.")
                        if info.get("command_message"):
                            try:
                                await info["command_message"].delete()
                            except discord.HTTPException:
                                logger.warning(f"Impossible de supprimer le message de commande lié au salon {voice_channel.name}.")
                        del self.tracked_channels[channel_id]
                        logger.info(f"Salon vocal {voice_channel.name} supprimé car vide.")
                    except discord.Forbidden:
                        logger.error(f"Permission refusée pour supprimer le salon vocal {voice_channel.name}.")
                    except discord.HTTPException as e:
                        logger.error(f"Erreur HTTP lors de la suppression du salon vocal {voice_channel.name}: {e}")
            else:
                self.tracked_channels[channel_id]["last_active"] = datetime.now(timezone.utc)

    @check_empty_channels.before_loop
    async def before_check_empty_channels(self):
        """Attend que le bot soit prêt avant de démarrer la tâche de vérification des salons vocaux."""
        await self.bot.wait_until_ready()
        logger.info("Task check_empty_channels démarrée.")

    async def add_tracked_channel(self, voice_channel: discord.VoiceChannel, invite_message: discord.Message):
        """Ajoute un salon vocal à la liste des salons suivis."""
        self.tracked_channels[voice_channel.id] = {
            "voice_channel": voice_channel,
            "invite_message": invite_message,
            "command_message": None,  # Si vous avez un message de commande spécifique
            "last_active": datetime.now(timezone.utc)
        }
        logger.info(f"Salon vocal {voice_channel.name} ajouté aux salons suivis.")

    async def remove_tracked_channel(self, voice_channel: discord.VoiceChannel):
        """Supprime un salon vocal de la liste des salons suivis."""
        if voice_channel.id in self.tracked_channels:
            del self.tracked_channels[voice_channel.id]
            logger.info(f"Salon vocal {voice_channel.name} retiré des salons suivis.")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        """Listener pour les mises à jour des états vocaux des membres."""
        if after.channel and after.channel.id not in self.tracked_channels:
            # Ajoutez ici la logique pour suivre de nouveaux salons si nécessaire
            pass  # Placeholder

async def setup(bot: commands.Bot) -> None:
    """Ajoute le Cog VoiceChannelCleanup au bot."""
    await bot.add_cog(VoiceChannelCleanup(bot))
    logger.info("VoiceChannelCleanup Cog chargé avec succès.")
