# cogs/utilities/request_manager.py
import asyncio
import heapq
import logging
from datetime import datetime, time
import discord

logger = logging.getLogger("discord.request_manager")

class Request:
    """
    Représente une requête d'exécution de commande.
    Contient :
    - interaction: l'interaction Discord
    - callback: la coroutine à exécuter pour la commande
    - priority: priorité numérique (plus bas = plus prioritaire dans un heap)
    - timestamp: moment de la création de la requête
    """
    def __init__(self, interaction: discord.Interaction, callback, priority: int):
        self.interaction = interaction
        self.callback = callback
        self.priority = priority
        self.timestamp = datetime.utcnow()

    def __lt__(self, other):
        # Comparaison par priorité puis par timestamp
        if self.priority == other.priority:
            # Si même priorité, requête la plus ancienne d'abord
            return self.timestamp < other.timestamp
        return self.priority < other.priority

class RequestManager:
    def __init__(self):
        self.queue = []
        self.lock = asyncio.Lock()
        self.processing_task = None
        self.shutdown_flag = False
        self.peak_hours = (time(hour=18), time(hour=22)) # exemple: heures de pointe entre 18h et 22h UTC
        self.request_count_per_hour = {}

    def start(self, bot: discord.Client):
        if self.processing_task is None:
            self.processing_task = bot.loop.create_task(self.process_requests())
            logger.info("RequestManager started.")

    def stop(self):
        self.shutdown_flag = True
        logger.info("RequestManager stopping...")

    async def process_requests(self):
        await asyncio.sleep(2)  # petit délai avant de commencer
        while not self.shutdown_flag:
            await asyncio.sleep(0.1)
            async with self.lock:
                if self.queue:
                    req = heapq.heappop(self.queue)
                else:
                    req = None
            if req:
                # Traiter la requête
                current_hour = datetime.utcnow().hour
                self.request_count_per_hour[current_hour] = self.request_count_per_hour.get(current_hour,0)+1

                # Exécuter la commande
                try:
                    # L'interaction a déjà été defer dans le décorateur, on utilise followup
                    await req.callback(req.interaction)
                except Exception as e:
                    logger.exception(f"Erreur lors de l'exécution de la commande: {e}")
                    await req.interaction.followup.send("Une erreur est survenue lors du traitement de votre requête.", ephemeral=True)
            else:
                # Rien à faire, on attend un peu
                await asyncio.sleep(0.5)

    def is_peak_hours(self) -> bool:
        now = datetime.utcnow().time()
        start, end = self.peak_hours
        return start <= now <= end

    def calculate_priority(self, interaction: discord.Interaction) -> int:
        """
        Calcule la priorité de la requête.
        Exemple:
        - Admin: priorité haute (valeur faible)
        - Booster: un peu moins haute
        - Bon joueur: moyen
        - Autres: bas
        - Si heures de pointe et pas admin, augmente la valeur (diminution de priorité)
        """
        # Plus la valeur est basse, plus c'est prioritaire.
        # On part d'une base:
        base_priority = 1000
        user = interaction.user
        guild = interaction.guild
        if guild:
            member = guild.get_member(user.id)
            if member:
                if member.guild_permissions.administrator:
                    base_priority = 100  # très haute priorité
                else:
                    booster_role = discord.utils.get(guild.roles, name="booster")
                    bon_joueur_role = discord.utils.get(guild.roles, name="bon joueur")
                    if booster_role and booster_role in member.roles:
                        base_priority = 300
                    elif bon_joueur_role and bon_joueur_role in member.roles:
                        base_priority = 500
                    else:
                        base_priority = 700

        # Si heures de pointe, on ajoute une pénalité aux non-admin
        if self.is_peak_hours() and not user.guild_permissions.administrator:
            base_priority += 200  # Priorité moindre pendant les heures de pointe pour non-admin

        return base_priority

    async def enqueue(self, interaction: discord.Interaction, callback):
        priority = self.calculate_priority(interaction)
        req = Request(interaction, callback, priority)
        async with self.lock:
            heapq.heappush(self.queue, req)

    def get_load_statistics(self):
        # Renvoie un dict du nb de requêtes par heure
        return self.request_count_per_hour


request_manager = RequestManager()

def setup_request_manager(bot):
    request_manager.start(bot)

def teardown_request_manager():
    request_manager.stop()


# Décorateur pour les commandes
def enqueue_request():
    def decorator(func):
        async def wrapper(self, interaction: discord.Interaction, *args, **kwargs):
            # On fait un defer de l'interaction car la réponse viendra plus tard
            await interaction.response.defer(ephemeral=True)
            await request_manager.enqueue(interaction, lambda i: func(self, i, *args, **kwargs))
        return wrapper
    return decorator
