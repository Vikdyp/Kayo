# cogs/utilities/request_manager.py

import asyncio
import heapq
from datetime import datetime, time
import discord
from functools import wraps
import logging
from typing import Callable, Any

logger = logging.getLogger("request_manager")


class Request:
    def __init__(self, interaction: discord.Interaction, callback: Callable[[discord.Interaction], Any], priority: int):
        self.interaction = interaction
        self.callback = callback
        self.priority = priority
        self.timestamp = datetime.utcnow()

    def __lt__(self, other):
        if self.priority == other.priority:
            return self.timestamp < other.timestamp
        return self.priority < other.priority


class RequestManager:
    def __init__(self):
        self.queue = []
        self.lock = asyncio.Lock()
        self.processing_task = None
        self.shutdown_flag = False
        self.peak_hours = (time(hour=18), time(hour=22))
        self.request_count_per_hour = {}

    def start(self, bot: discord.Client):
        if self.processing_task is None or self.processing_task.done():
            self.processing_task = bot.loop.create_task(self.process_requests())
            logger.debug("RequestManager processing task started.")

    def stop(self):
        self.shutdown_flag = True
        logger.debug("RequestManager stopping...")

    async def process_requests(self):
        logger.debug("Request processing loop started.")
        await asyncio.sleep(2)  # Petit délai avant de commencer
        while not self.shutdown_flag:
            async with self.lock:
                if self.queue:
                    req = heapq.heappop(self.queue)
                    logger.debug(f"Dequeued request: interaction={req.interaction.id}, priority={req.priority}")
                else:
                    req = None
            if req:
                try:
                    await req.callback(req.interaction)
                except Exception as e:
                    logger.exception(f"Error processing request {req.interaction.id}: {e}")
                    try:
                        await req.interaction.followup.send(
                            "Une erreur est survenue lors du traitement de votre demande.", ephemeral=True
                        )
                    except Exception as send_error:
                        logger.error(f"Échec de l'envoi de la réponse d'erreur: {send_error}")
            else:
                await asyncio.sleep(0.5)

    def is_peak_hours(self) -> bool:
        now = datetime.utcnow().time()
        start, end = self.peak_hours
        return start <= now <= end

    def calculate_priority(self, interaction: discord.Interaction) -> int:
        """Calcule la priorité d'une requête en fonction des rôles de l'utilisateur et des heures de pointe."""
        base_priority = 1000
        user = interaction.user

        if user.guild_permissions.administrator:
            base_priority = 100
        else:
            booster_role = discord.utils.get(interaction.guild.roles, name="booster")
            bon_joueur_role = discord.utils.get(interaction.guild.roles, name="bon joueur")
            if booster_role and booster_role in user.roles:
                base_priority = 300
            elif bon_joueur_role and bon_joueur_role in user.roles:
                base_priority = 500
            else:
                base_priority = 700

        if self.is_peak_hours() and not user.guild_permissions.administrator:
            base_priority += 200
        return base_priority

    async def enqueue(self, interaction: discord.Interaction, callback: Callable[[discord.Interaction], Any]):
        """Ajoute une requête à la file d'attente avec une priorité calculée."""
        priority = self.calculate_priority(interaction)
        req = Request(interaction, callback, priority)
        async with self.lock:
            heapq.heappush(self.queue, req)
            logger.debug(f"Request added to queue: interaction={interaction.id}, priority={priority}")

    def get_load_statistics(self):
        return self.request_count_per_hour


request_manager = RequestManager()


def setup_request_manager(bot: discord.Client):
    """Initialise et démarre le RequestManager avec le bot."""
    request_manager.start(bot)
    logger.info("RequestManager setup complete.")


def teardown_request_manager():
    """Arrête le RequestManager."""
    request_manager.stop()
    logger.info("RequestManager teardown complete.")


def enqueue_request():
    """Décorateur pour enqueuer les commandes en utilisant le RequestManager."""

    def decorator(func):
        @wraps(func)
        async def wrapper(self, interaction: discord.Interaction, *args, **kwargs):
            try:
                await interaction.response.defer(ephemeral=True)
                logger.debug(f"Command deferred: interaction={interaction.id}")
                await request_manager.enqueue(interaction, lambda i: func(self, i, *args, **kwargs))
            except Exception as e:
                logger.exception(f"Failed to enqueue request: {e}")
        return wrapper
    return decorator
