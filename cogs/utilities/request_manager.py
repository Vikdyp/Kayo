import asyncio
import heapq
import logging
from datetime import datetime, time
import discord
from discord import app_commands
from functools import wraps

logger = logging.getLogger("discord.request_manager")

class Request:
    def __init__(self, interaction: discord.Interaction, callback, priority: int):
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
        if self.processing_task is None:
            self.processing_task = bot.loop.create_task(self.process_requests())
            logger.info("RequestManager started.")

    def stop(self):
        self.shutdown_flag = True
        logger.info("RequestManager stopping...")

    async def process_requests(self):
        await asyncio.sleep(2)
        while not self.shutdown_flag:
            await asyncio.sleep(0.1)
            async with self.lock:
                if self.queue:
                    req = heapq.heappop(self.queue)
                else:
                    req = None
            if req:
                current_hour = datetime.utcnow().hour
                self.request_count_per_hour[current_hour] = self.request_count_per_hour.get(current_hour, 0) + 1
                try:
                    await req.callback(req.interaction)
                except Exception as e:
                    logger.exception(f"Erreur lors de l'exécution de la commande: {e}")
                    await req.interaction.followup.send(
                        "Une erreur est survenue lors du traitement de votre requête.", ephemeral=True
                    )
            else:
                await asyncio.sleep(0.5)

    def is_peak_hours(self) -> bool:
        now = datetime.utcnow().time()
        start, end = self.peak_hours
        return start <= now <= end

    def calculate_priority(self, interaction: discord.Interaction) -> int:
        base_priority = 1000
        user = interaction.user
        guild = interaction.guild
        if guild:
            member = guild.get_member(user.id)
            if member:
                if member.guild_permissions.administrator:
                    base_priority = 100
                else:
                    booster_role = discord.utils.get(guild.roles, name="booster")
                    bon_joueur_role = discord.utils.get(guild.roles, name="bon joueur")
                    if booster_role and booster_role in member.roles:
                        base_priority = 300
                    elif bon_joueur_role and bon_joueur_role in member.roles:
                        base_priority = 500
                    else:
                        base_priority = 700
        if self.is_peak_hours() and not user.guild_permissions.administrator:
            base_priority += 200
        return base_priority

    async def enqueue(self, interaction: discord.Interaction, callback):
        priority = self.calculate_priority(interaction)
        req = Request(interaction, callback, priority)
        async with self.lock:
            heapq.heappush(self.queue, req)

    def get_load_statistics(self):
        return self.request_count_per_hour


request_manager = RequestManager()

def setup_request_manager(bot):
    request_manager.start(bot)

def teardown_request_manager():
    request_manager.stop()


def enqueue_request():
    def decorator(func):
        @wraps(func)
        async def wrapper(self, interaction: discord.Interaction, *args, **kwargs):
            await interaction.response.defer(ephemeral=True)
            await request_manager.enqueue(interaction, lambda i: func(self, i, *args, **kwargs))
        return wrapper
    return decorator
