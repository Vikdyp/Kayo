# utils/request_manager.py
import asyncio
import heapq
from datetime import datetime, timedelta
import discord
from functools import wraps
import logging
from typing import Callable, Any, Optional

logger = logging.getLogger("request_manager")


# 1) Définir les types de requêtes
#    - Classique   => expire 30s,  priorité de base 2
#    - Urgent      => expire 60s,  priorité de base 3
#    - Passive     => expire 24h,  priorité de base 1

REQUEST_TYPES = {
    "CLASSIC": {
        "expire_seconds": 30,
        "base_priority": 2
    },
    "URGENT": {
        "expire_seconds": 60,
        "base_priority": 3
    },
    "PASSIVE": {
        "expire_seconds": 24 * 3600,  # 24h
        "base_priority": 1
    },
}


class Request:
    """
    Représente une requête mise en file d'attente.
    """
    def __init__(
        self,
        interaction: discord.Interaction,
        callback: Callable[[discord.Interaction], Any],
        request_type: str,
        is_admin: bool = False
    ):
        self.interaction = interaction
        self.callback = callback

        # On prend la config du type de requête :
        req_info = REQUEST_TYPES.get(request_type.upper(), REQUEST_TYPES["CLASSIC"])

        self.request_type = request_type.upper()
        self.timestamp = datetime.utcnow()

        # Date d'expiration selon le type
        self.expiry = self.timestamp + timedelta(seconds=req_info["expire_seconds"])

        # Priorité de base (plus la priorité est petite, plus elle sera traitée en premier)
        # On peut ajuster la logique : plus c'est urgent, plus le nombre est faible,
        # OU alors on fait l'inverse. À adapter selon ton usage.
        base_priority = req_info["base_priority"]

        # Si c'est un admin, on décrémente la priorité pour passer au-dessus
        # (par exemple, -1 : ainsi un admin "urgent" aurait une priority = 1
        #  alors qu'un user normal "urgent" est à 2, un user "classique" est à 1
        #  => il faut clarifier la hiérarchie de traitement que tu souhaites)
        if is_admin:
            base_priority -= 1

        self.priority = base_priority

    def __lt__(self, other: "Request"):
        """
        Permet de comparer deux requêtes dans le heap selon leur priorité,
        puis en cas d’égalité, selon le timestamp (la plus ancienne passe d'abord).
        """
        if self.priority == other.priority:
            return self.timestamp < other.timestamp
        return self.priority < other.priority

    def is_expired(self) -> bool:
        """Vérifie si la requête a expiré."""
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
        """
        Démarre les workers (tasks) qui traitent la queue.
        """
        if not self.workers:
            for _ in range(self.worker_count):
                worker = bot.loop.create_task(self.process_requests())
                self.workers.append(worker)
            logger.debug(f"{self.worker_count} RequestManager processing tasks started.")

    def stop(self):
        """
        Arrête les workers.
        """
        self.shutdown_flag = True
        for worker in self.workers:
            worker.cancel()
        logger.debug("RequestManager stopping...")

    async def process_requests(self):
        """
        Boucle de traitement pour chaque worker.
        Récupère les requêtes dans le heap, vérifie l'expiration, exécute les callbacks, etc.
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
                    # Mise à jour des stats
                    current_hour = datetime.utcnow().hour
                    self.request_count_per_hour[current_hour] = (
                        self.request_count_per_hour.get(current_hour, 0) + 1
                    )
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
        Cherche un rôle en cache local ou dans la guild.
        """
        # Cache basique, pas de gestion d’invalidation
        if role_name not in self.role_cache:
            self.role_cache[role_name] = discord.utils.get(guild.roles, name=role_name)
        return self.role_cache.get(role_name)

    async def is_admin_user(self, user: discord.Member) -> bool:
        """
        Détermine si un utilisateur est admin au sens de la table roles_configurations.
        Par exemple, si la table roles_configurations contient un `role_name = 'admin'`,
        on vérifie si le user a ce rôle.
        
        -> À adapter selon ta logique de base de données. 
           Idéalement, on requête la DB pour connaître l'ID de rôle 'admin'
           puis on check si user.roles contient ce rôle Discord.

        Ici on part du principe que tu as un 'admin' quelque part, 
        ou que tu feras une requête si besoin.
        """
        # EXEMPLE : À adapter si tu as une vraie requête DB...
        # row = await database.fetch_one(
        #    "SELECT role_id FROM roles_configurations WHERE role_name = 'admin' AND server_id = $1",
        #    [user.guild.id]
        # )
        # if row is None:
        #    return False
        #
        # role_id = row['role_id']
        # return any(r.id == role_id for r in user.roles)

        # Version simplifiée => on suppose que "admin" est le nom exact du rôle
        admin_role = discord.utils.get(user.guild.roles, name="Modérateur")
        if not admin_role:
            return user.guild_permissions.administrator  # fallback
        return admin_role in user.roles

    async def enqueue(
        self,
        interaction: discord.Interaction,
        callback: Callable[[discord.Interaction], Any],
        request_type: str = "CLASSIC"
    ):
        """
        Ajoute une requête dans la file d'attente.
        
        :param request_type: "CLASSIC" | "URGENT" | "PASSIVE"
        """
        # Vérifier si l'utilisateur est considéré comme "admin" (selon DB ou la guild)
        user = interaction.user
        is_admin = await self.is_admin_user(user)

        # Crée la requête
        req = Request(interaction, callback, request_type, is_admin=is_admin)

        async with self.lock:
            heapq.heappush(self.queue, req)
            logger.debug(
                f"Request added to queue: interaction={interaction.id}, "
                f"type={request_type}, priority={req.priority}, is_admin={is_admin}"
            )

    def get_load_statistics(self):
        """
        Retourne un dict {heure: nb_requetes}.
        """
        return self.request_count_per_hour


# Instance globale
request_manager = RequestManager()


def setup_request_manager(bot: discord.Client):
    """
    À appeler lors du démarrage du bot (ex: dans ton main).
    """
    request_manager.start(bot)
    logger.info("RequestManager setup complete.")


def teardown_request_manager():
    """
    À appeler lors de l'extinction du bot (ex: dans on_shutdown).
    """
    request_manager.stop()
    logger.info("RequestManager teardown complete.")


def enqueue_request(request_type: str = "CLASSIC"):
    def decorator(func):
        @wraps(func)
        async def wrapper(self, interaction: discord.Interaction, *args, **kwargs):
            try:
                # On défère la réponse, pour laisser le bot travailler
                await interaction.response.defer(ephemeral=True)
                
                # Message spécifique si la requête est considérée basse priorité
                # (ici on traite "PASSIVE" comme 'basses priorités')
                if request_type.upper() in ("PASSIVE"):
                    await interaction.followup.send(
                        "Votre requête a été reçue et sera traitée dès que possible. "
                        "Le délai de traitement peut atteindre 24h.",
                        ephemeral=True
                    )
                else:
                    # Pour le type 'URGENT' ou autre
                    await interaction.followup.send(
                        "Envoi de la commande… Veuillez patienter.",
                        ephemeral=True
                    )

                # Ajout dans la file
                logger.debug(
                    f"Enqueuing request for {func.__name__}, "
                    f"interaction={interaction.id}, type={request_type}"
                )
                await request_manager.enqueue(
                    interaction,
                    lambda i: func(self, i, *args, **kwargs),
                    request_type
                )
            except Exception as e:
                logger.exception(f"Failed to enqueue request: {e}")
                # En cas d'erreur
                try:
                    await interaction.followup.send(
                        "Impossible d'enregistrer votre demande.",
                        ephemeral=True
                    )
                except:
                    pass

        return wrapper
    return decorator
