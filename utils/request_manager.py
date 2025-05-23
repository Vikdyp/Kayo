import asyncio
import heapq
from datetime import datetime, timedelta
import discord
from functools import wraps
import logging
from typing import Callable, Any, Optional, Dict

logger = logging.getLogger("request_manager")

# Définition des types de requêtes
# - CLASSIC: expire 30s, priorité de base 2
# - URGENT:  expire 60s, priorité de base 3
# - PASSIVE: expire 24h, priorité de base 1
# - FAST:    expire 10s, priorité de base 5
REQUEST_TYPES: Dict[str, Dict[str, Any]] = {
    "CLASSIC": {
        "expire_seconds": 30,
        "base_priority": 2,
    },
    "URGENT": {
        "expire_seconds": 60,
        "base_priority": 3,
    },
    "PASSIVE": {
        "expire_seconds": 24 * 3600,  # 24h
        "base_priority": 1,
    },
    "FAST": {
        "expire_seconds": 10,
        "base_priority": 5,
    },
}


class Request:
    """
    Représente une requête mise en file d'attente.
    Elle stocke l'interaction, la fonction callback à exécuter, le type de requête,
    ainsi que sa priorité et sa date d'expiration.
    """
    def __init__(
        self,
        interaction: discord.Interaction,
        callback: Callable[[discord.Interaction], Any],
        request_type: str,
        is_admin: bool = False
    ) -> None:
        self.interaction: discord.Interaction = interaction
        self.callback: Callable[[discord.Interaction], Any] = callback

        # Récupération de la configuration selon le type de requête.
        req_info = REQUEST_TYPES.get(request_type.upper(), REQUEST_TYPES["CLASSIC"])
        self.request_type: str = request_type.upper()
        self.timestamp: datetime = datetime.utcnow()
        self.expiry: datetime = self.timestamp + timedelta(seconds=req_info["expire_seconds"])

        # Calcul de la priorité (une priorité plus faible signifie un traitement plus rapide).
        base_priority: int = req_info["base_priority"]
        if is_admin:
            base_priority -= 1  # Un admin bénéficie d'une priorité améliorée.
        self.priority: int = base_priority

    def __lt__(self, other: "Request") -> bool:
        """
        Permet la comparaison entre deux requêtes dans le heap.
        En cas d'égalité de priorité, la plus ancienne (timestamp) est traitée en premier.
        """
        if self.priority == other.priority:
            return self.timestamp < other.timestamp
        return self.priority < other.priority

    def is_expired(self) -> bool:
        """Retourne True si la requête a expiré."""
        return datetime.utcnow() >= self.expiry


class RequestManager:
    """
    Gère la file d'attente des requêtes et leur traitement par des workers.
    Permet d'enfiler des requêtes, de suivre des statistiques et de gérer une file de priorité.
    """
    def __init__(self, worker_count: int = 5) -> None:
        self.queue: list[Request] = []
        self.lock: asyncio.Lock = asyncio.Lock()
        self.workers: list[asyncio.Task] = []
        self.shutdown_flag: bool = False
        self.worker_count: int = worker_count
        self.role_cache: Dict[str, discord.Role] = {}
        self.request_count_per_hour: Dict[int, int] = {}

    def start(self, bot: discord.Client) -> None:
        """
        Démarre les workers qui traiteront la file d'attente.
        """
        if not self.workers:
            for _ in range(self.worker_count):
                worker = bot.loop.create_task(self.process_requests())
                self.workers.append(worker)
            logger.debug(f"{self.worker_count} RequestManager processing tasks started.")

    def stop(self) -> None:
        """
        Arrête tous les workers de traitement.
        """
        self.shutdown_flag = True
        for worker in self.workers:
            worker.cancel()
        logger.debug("RequestManager stopping...")

    async def process_requests(self) -> None:
        """
        Boucle de traitement d'une requête : récupère la requête la plus prioritaire,
        vérifie son expiration, exécute son callback et met à jour les statistiques.
        """
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
                                "Votre demande a expiré avant d'avoir pu être traitée.",
                                ephemeral=True
                            )
                        except Exception as send_error:
                            logger.error(f"Échec de l'envoi du message d'expiration: {send_error}")
                        req = None
                        continue
                    break
            if req:
                logger.debug(
                    f"Processing request: interaction={req.interaction.id}, "
                    f"type={req.request_type}, priority={req.priority}"
                )
                try:
                    await req.callback(req.interaction)
                    # Mise à jour des statistiques de traitement.
                    current_hour = datetime.utcnow().hour
                    self.request_count_per_hour[current_hour] = self.request_count_per_hour.get(current_hour, 0) + 1
                    logger.debug(f"Request processed successfully: interaction={req.interaction.id}")
                except Exception as e:
                    logger.exception(f"Error processing request {req.interaction.id}: {e}")
                    try:
                        await req.interaction.followup.send(
                            "Une erreur est survenue lors du traitement de votre demande. erreur 101",
                            ephemeral=True
                        )
                    except Exception as send_error:
                        logger.error(f"Échec de l'envoi de la réponse d'erreur: {send_error}")
            else:
                await asyncio.sleep(0.1)

    def get_role(self, guild: discord.Guild, role_name: str) -> Optional[discord.Role]:
        """
        Retourne un rôle en vérifiant d'abord dans le cache, puis dans la guild.
        """
        if role_name not in self.role_cache:
            self.role_cache[role_name] = discord.utils.get(guild.roles, name=role_name)
        return self.role_cache.get(role_name)

    async def is_admin_user(self, user: discord.Member) -> bool:
        """
        Vérifie si l'utilisateur possède le rôle "Modérateur" ou a les permissions administrateur.
        """
        admin_role = discord.utils.get(user.guild.roles, name="Modérateur")
        if not admin_role:
            return user.guild_permissions.administrator
        return admin_role in user.roles

    async def enqueue(
        self,
        interaction: discord.Interaction,
        callback: Callable[[discord.Interaction], Any],
        request_type: str = "CLASSIC"
    ) -> None:
        """
        Ajoute une requête dans la file d'attente.
        
        :param request_type: "CLASSIC", "URGENT", "PASSIVE" ou "FAST"
        """
        user = interaction.user
        is_admin: bool = await self.is_admin_user(user)
        req = Request(interaction, callback, request_type, is_admin=is_admin)
        async with self.lock:
            heapq.heappush(self.queue, req)
            logger.debug(
                f"Request added to queue: interaction={interaction.id}, "
                f"type={request_type.upper()}, priority={req.priority}, is_admin={is_admin}"
            )

    def get_load_statistics(self) -> Dict[int, int]:
        """
        Retourne un dictionnaire contenant le nombre de requêtes traitées par heure.
        """
        return self.request_count_per_hour


# Instance globale du RequestManager
request_manager = RequestManager()


def setup_request_manager(bot: discord.Client) -> None:
    """
    À appeler lors du démarrage du bot (par exemple, dans le main).
    """
    request_manager.start(bot)
    logger.info("RequestManager setup complete.")


def teardown_request_manager() -> None:
    """
    À appeler lors de l'arrêt du bot (par exemple, dans on_shutdown).
    """
    request_manager.stop()
    logger.info("RequestManager teardown complete.")


def enqueue_request(request_type: str = "CLASSIC"):
    """
    Décorateur pour enfiler une requête avec un defer automatique de la réponse et un message de suivi.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(self, interaction: discord.Interaction, *args, **kwargs) -> None:
            try:
                await interaction.response.defer(ephemeral=True)
                if request_type.upper() == "PASSIVE":
                    await interaction.followup.send(
                        "Votre requête a été reçue et sera traitée dès que possible. Le délai de traitement peut atteindre 24h.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "Envoi de la commande… Veuillez patienter.",
                        ephemeral=True
                    )
                logger.debug(
                    f"Enqueuing request for {func.__name__}, interaction={interaction.id}, type={request_type.upper()}"
                )
                await request_manager.enqueue(
                    interaction,
                    lambda i: func(self, i, *args, **kwargs),
                    request_type
                )
            except Exception as e:
                logger.exception(f"Failed to enqueue request: {e}")
                try:
                    await interaction.followup.send(
                        "Impossible d'enregistrer votre demande.",
                        ephemeral=True
                    )
                except Exception:
                    pass
        return wrapper
    return decorator


def enqueue_button_request(request_type: str = "CLASSIC"):
    """
    Décorateur pour enfiler une requête depuis un bouton.
    Contrairement à enqueue_request, il ne gère pas le defer ni l'envoi automatique de messages.
    Vous devez gérer ces aspects dans la fonction du bouton.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(self, interaction: discord.Interaction, *args, **kwargs) -> None:
            try:
                logger.debug(
                    f"Enqueuing (button) request for {func.__name__}, interaction={interaction.id}, type={request_type.upper()}"
                )
                await request_manager.enqueue(
                    interaction,
                    lambda i: func(self, i, *args, **kwargs),
                    request_type
                )
            except Exception as e:
                logger.exception(f"Failed to enqueue button request: {e}")
                try:
                    await interaction.followup.send(
                        "Impossible d'enregistrer votre demande (bouton).",
                        ephemeral=True
                    )
                except Exception:
                    pass
        return wrapper
    return decorator
