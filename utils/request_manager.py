# cogs/utilities/request_manager.py

import asyncio
import heapq
from datetime import datetime, timedelta
import discord
from functools import wraps
import logging
from typing import Callable, Any, Optional

logger = logging.getLogger("request_manager")


class Request:
    def __init__(self, interaction: discord.Interaction, callback: Callable[[discord.Interaction], Any], priority: int):
        self.interaction = interaction
        self.callback = callback
        self.priority = priority
        self.timestamp = datetime.utcnow()
        self.expiry = self.timestamp + timedelta(seconds=30)  # Expire après 30 secondes

    def __lt__(self, other):
        # Priorité plus basse signifie priorité plus haute
        if self.priority == other.priority:
            return self.timestamp < other.timestamp
        return self.priority < other.priority

    def is_expired(self) -> bool:
        return datetime.utcnow() >= self.expiry


class RequestManager:
    def __init__(self, worker_count: int = 5):
        self.queue = []
        self.lock = asyncio.Lock()
        self.workers = []
        self.shutdown_flag = False
        self.worker_count = worker_count
        self.role_cache = {}
        self.request_count_per_hour = {}

    def start(self, bot: discord.Client):
        if not self.workers:
            for _ in range(self.worker_count):
                worker = bot.loop.create_task(self.process_requests())
                self.workers.append(worker)
            logger.debug(f"{self.worker_count} RequestManager processing tasks started.")

    def stop(self):
        self.shutdown_flag = True
        for worker in self.workers:
            worker.cancel()
        logger.debug("RequestManager stopping...")

    async def process_requests(self):
        logger.debug("Worker started.")
        while not self.shutdown_flag:
            req: Optional[Request] = None
            async with self.lock:
                while self.queue:
                    req = heapq.heappop(self.queue)
                    if req.is_expired():
                        logger.warning(f"Request expired and removed: interaction={req.interaction.id}")
                        try:
                            await req.interaction.followup.send(
                                "Votre demande a expiré avant d'avoir pu être traitée.", ephemeral=True
                            )
                        except Exception as send_error:
                            logger.error(f"Échec de l'envoi du message d'expiration: {send_error}")
                        req = None
                        continue
                    break  # Requête valide trouvée
            if req:
                try:
                    await req.callback(req.interaction)
                    # Mettre à jour les statistiques
                    current_hour = datetime.utcnow().hour
                    self.request_count_per_hour[current_hour] = self.request_count_per_hour.get(current_hour, 0) + 1
                except Exception as e:
                    logger.exception(f"Error processing request {req.interaction.id}: {e}")
                    try:
                        await req.interaction.followup.send(
                            "Une erreur est survenue lors du traitement de votre demande.", ephemeral=True
                        )
                    except Exception as send_error:
                        logger.error(f"Échec de l'envoi de la réponse d'erreur: {send_error}")
            else:
                await asyncio.sleep(0.1)  # Délai réduit pour réagir plus rapidement

    def get_role(self, guild: discord.Guild, role_name: str) -> Optional[discord.Role]:
        if role_name not in self.role_cache:
            self.role_cache[role_name] = discord.utils.get(guild.roles, name=role_name)
        return self.role_cache.get(role_name)

    def calculate_priority(self, interaction: discord.Interaction) -> int:
        """Calcule la priorité d'une requête en fonction des rôles de l'utilisateur."""
        base_priority = 1000
        user = interaction.user

        if user.guild_permissions.administrator:
            base_priority = 100
        else:
            booster_role = self.get_role(interaction.guild, "booster")
            bon_joueur_role = self.get_role(interaction.guild, "bon joueur")
            if booster_role and booster_role in user.roles:
                base_priority = 300
            elif bon_joueur_role and bon_joueur_role in user.roles:
                base_priority = 500
            else:
                base_priority = 700

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
