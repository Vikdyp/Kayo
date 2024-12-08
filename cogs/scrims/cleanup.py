# cogs/scrims/cleanup.py

import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta

from ..utilities.utils import load_json, save_json

logger = logging.getLogger('discord.scrims.cleanup')

def make_scrims_key(rank: str, list_index: int) -> str:
    """Creates a unique key for scrims data."""
    return f"{rank}-{list_index}"

class ScrimCleanup(commands.Cog):
    """Cog pour nettoyer les salons vocaux après les scrims."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.scrims_data_file = "data/scrims_data.json"
        self.scrims_data: Dict[str, Dict[str, Any]] = {}
        self.data_lock = asyncio.Lock()

        self.bot.loop.create_task(self.load_scrims_data())
        self.cleanup_task.start()

    async def load_scrims_data(self) -> None:
        """Charge les données des scrims depuis le fichier JSON."""
        async with self.data_lock:
            self.scrims_data = await load_json(self.scrims_data_file)
        logger.info("ScrimCleanup: Données des scrims chargées avec succès.")

    async def save_scrims_data(self) -> None:
        """Sauvegarde les données des scrims dans le fichier JSON."""
        async with self.data_lock:
            await save_json_atomic(self.scrims_data, self.scrims_data_file)
        logger.info("ScrimCleanup: Données des scrims sauvegardées avec succès.")

    @tasks.loop(minutes=5)
    async def cleanup_task(self):
        """Tâche périodique pour nettoyer les salons vocaux terminés."""
        async with self.data_lock:
            now = datetime.now(timezone.utc)
            to_delete = []

            for scrims_key, scrim in self.scrims_data.items():
                end_time_str = scrim.get("end_time")
                if end_time_str:
                    end_time = datetime.fromisoformat(end_time_str)
                    if now > end_time + timedelta(minutes=30):  # 30 minutes après la fin
                        to_delete.append(scrims_key)

            for scrims_key in to_delete:
                scrim = self.scrims_data.get(scrims_key)
                if scrim:
                    for channel_id in scrim.get("channels", []):
                        channel = self.bot.get_channel(channel_id)
                        if channel:
                            try:
                                await channel.delete()
                                logger.info(f"Salon vocal {channel.name} supprimé après les scrims.")
                            except discord.Forbidden:
                                logger.error(f"Permission refusée pour supprimer le salon vocal {channel.name}.")
                            except discord.HTTPException as e:
                                logger.error(f"Erreur HTTP lors de la suppression du salon vocal {channel.name}: {e}")
                    del self.scrims_data[scrims_key]
            if to_delete:
                await self.save_scrims_data()

    @cleanup_task.before_loop
    async def before_cleanup_task(self):
        """Attend que le bot soit prêt avant de démarrer la tâche de nettoyage."""
        await self.bot.wait_until_ready()
        logger.info("Tâche de nettoyage des scrims démarrée.")

    async def setup(self, bot: commands.Bot) -> None:
        """Ajoute le Cog ScrimCleanup au bot."""
        await bot.add_cog(ScrimCleanup(bot))
        logger.info("ScrimCleanup Cog chargé avec succès.")
