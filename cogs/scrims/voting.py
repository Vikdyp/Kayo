# cogs/scrims/voting.py

import asyncio
import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, timezone

from cogs.utilities.utils import load_json, save_json, save_json_atomic

logger = logging.getLogger('discord.scrims.voting')

def make_scrims_key(rank: str, list_index: int) -> str:
    """Creates a unique key for scrims data."""
    return f"{rank}-{list_index}"

class ScrimVoting(commands.Cog):
    """Cog pour gérer les votes sur l'heure des scrims."""

    dependencies = []

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_file = 'data/config.json'
        self.scrims_data_file = "data/scrims_data.json"
        self.config: Dict[str, Any] = {}
        self.scrims_data: Dict[str, Dict[str, Any]] = {}
        self.data_lock = asyncio.Lock()

        self.bot.loop.create_task(self.load_config())

    async def load_config(self) -> None:
        """Charge la configuration et les données des scrims depuis les fichiers JSON."""
        async with self.data_lock:
            self.config = await load_json(self.config_file)
            self.scrims_data = await load_json(self.scrims_data_file)
        logger.info("ScrimVoting: Configuration et données des scrims chargées avec succès.")

    async def save_scrims_data(self) -> None:
        """Sauvegarde les données des scrims dans le fichier JSON."""
        async with self.data_lock:
            await save_json_atomic(self.scrims_data, self.scrims_data_file)
        logger.info("ScrimVoting: Données des scrims sauvegardées avec succès.")

    @commands.Cog.listener()
    async def on_vote(self, interaction: discord.Interaction, rank: str, list_index: int, vote: int) -> None:
        """Gère les votes des joueurs pour l'heure des scrims."""
        scrims_key = make_scrims_key(rank, list_index)
        async with self.data_lock:
            scrim = self.scrims_data.get(scrims_key)
            if not scrim:
                await interaction.response.send_message(
                    "Scrim introuvable ou déjà finalisé.",
                    ephemeral=True
                )
                logger.warning(f"Vote reçu pour un scrim introuvable: {scrims_key}")
                return

            user_id = str(interaction.user.id)
            if scrim["voted"].get(user_id, False):
                await interaction.response.send_message(
                    "Vous avez déjà voté pour cette scrim.",
                    ephemeral=True
                )
                logger.info(f"{interaction.user} a tenté de voter plusieurs fois pour le scrim {scrims_key}.")
                return

            scrim["voted"][user_id] = True
            scrim["votes"][vote] += 1
            await self.save_scrims_data()

            await interaction.response.send_message(
                f"Votre vote pour {vote}:00 a été enregistré.",
                ephemeral=True
            )
            logger.info(f"{interaction.user} a voté pour {vote}:00 dans le scrim {scrims_key}.")

            # Optionnel: Vérifier si tous les joueurs ont voté et fixer l'heure des scrims
            if all(voted for voted in scrim["voted"].values()):
                selected_hour = self.calculate_best_vote(scrim["votes"])
                scrim["selected_hour"] = selected_hour
                await self.save_scrims_data()
                await self.notify_scrim_time(guild=scrim.get("guild_id"), channel_ids=scrim.get("channels", []), hour=selected_hour)

    def calculate_best_vote(self, votes: Dict[int, int]) -> int:
        """Calcule l'heure la plus votée pour les scrims."""
        if not votes:
            return 18  # Heure par défaut
        return max(votes, key=votes.get)

    async def notify_scrim_time(self, guild: int, channel_ids: List[int], hour: int) -> None:
        """Notifie les joueurs de l'heure choisie pour les scrims."""
        guild_obj = self.bot.get_guild(guild)
        if not guild_obj:
            logger.error(f"Guild avec l'ID {guild} non trouvée pour notifier l'heure des scrims.")
            return

        for channel_id in channel_ids:
            channel = guild_obj.get_channel(channel_id)
            if channel:
                await channel.send(f"Les scrims commenceront à {hour}:00.")
                logger.info(f"Notification envoyée dans le salon {channel.name} pour l'heure des scrims à {hour}:00.")
            else:
                logger.warning(f"Salon avec l'ID {channel_id} non trouvé dans la guild {guild_obj.name}.")

async def setup(bot: commands.Bot) -> None:
    """Ajoute le Cog ScrimVoting au bot."""
    await bot.add_cog(ScrimVoting(bot))
    logger.info("ScrimVoting Cog chargé avec succès.")
