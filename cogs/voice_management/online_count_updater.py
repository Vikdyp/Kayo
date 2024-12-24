# cogs/voice_management/online_count_updater.py

import discord
import logging
from discord.ext import tasks

from cogs.voice_management.services.rank_service import RankService

logger = logging.getLogger("rank_updater")

class RankUpdater:
    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.task = self._task_loop  # Référence à la tâche

    def start(self):
        """Démarre la tâche de mise à jour."""
        if not self.task.is_running():
            self.task.start()
            logger.info("Tâche périodique de mise à jour des salons démarrée.")

    def stop(self):
        """Arrête proprement la tâche."""
        if self.task.is_running():
            self.task.cancel()
            logger.info("Tâche périodique de mise à jour des salons arrêtée.")

    @tasks.loop(minutes=5)
    async def _task_loop(self):
        """Tâche principale pour mettre à jour les salons des rangs."""
        logger.info("Exécution de la tâche de mise à jour des salons.")
        for guild in self.bot.guilds:
            config = await RankService.get_config(guild.id)
            roles_config = config.get("roles", {})
            channels_config = config.get("channels", {})

            ranks = ["fer", "bronze", "argent", "or", "platine", "diamant", "ascendant", "immortel", "radiant"]

            for rank in ranks:
                role_id = roles_config.get(rank)
                channel_id = channels_config.get(rank)

                if not role_id or not channel_id:
                    logger.warning(f"Rang {rank.capitalize()} : rôle ou salon non configuré pour le serveur {guild.id}.")
                    continue

                role = guild.get_role(role_id)
                channel = guild.get_channel(channel_id)

                if not role:
                    logger.warning(f"Rôle {rank.capitalize()} introuvable dans le serveur {guild.id}.")
                    continue

                if not channel:
                    logger.warning(f"Salon {rank.capitalize()} introuvable dans le serveur {guild.id}.")
                    continue

                online_members = [member for member in role.members if member.status != discord.Status.offline]
                online_count = len(online_members)

                new_channel_name = f"{rank.capitalize()} - {online_count} en ligne"
                if channel.name != new_channel_name:
                    try:
                        await channel.edit(name=new_channel_name)
                        logger.info(f"Nom du salon {channel.name} mis à jour pour le serveur {guild.id}: {new_channel_name}.")
                    except Exception as e:
                        logger.error(f"Erreur lors de la mise à jour du salon {channel.name} pour le serveur {guild.id} : {e}")
                else:
                    logger.debug(f"Nom du salon {channel.name} déjà à jour.")

    @_task_loop.before_loop
    async def before_task_loop(self):
        """Attendez que le bot soit prêt avant de démarrer la tâche."""
        logger.info("Attente que le bot soit prêt pour démarrer la tâche de mise à jour des salons.")
        await self.bot.wait_until_ready()

# Singleton
rank_updater = RankUpdater(None)

def setup_rank_updater(bot: discord.Client):
    """Initialise et démarre le RankUpdater avec le bot."""
    rank_updater.bot = bot
    rank_updater.start()
    logger.info("RankUpdater setup complete.")

def teardown_rank_updater():
    """Arrête le RankUpdater."""
    rank_updater.stop()
    logger.info("RankUpdater teardown complete.")
