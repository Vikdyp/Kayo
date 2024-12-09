import discord
from discord.ext import commands
import logging
import os
from dotenv import load_dotenv
import asyncio

load_dotenv()

if not os.path.exists('logs'):
    os.makedirs('logs')

logging.basicConfig(
    level=logging.INFO,
    format="\n%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(filename='logs/bot.log', encoding='utf-8', mode='a'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger('discord.main')

intents = discord.Intents.default()
intents.members = True
intents.voice_states = True
intents.guilds = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, description="Bot complet")

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

if not DISCORD_BOT_TOKEN:
    logger.critical("Le token du bot n'est pas défini. Veuillez vérifier le fichier .env.")
    exit(1)

async def load_all_cogs():
    # Charge tous les cogs
    for folder in ["utilities", "reputation", "economy", "tournaments", "scrims", "voice_management", "moderation", "role_management", "configuration"]:
        cogs_dir = f"./cogs/{folder}"
        if os.path.exists(cogs_dir):
            for filename in os.listdir(cogs_dir):
                if filename.endswith(".py"):
                    extension = f"cogs.{folder}.{filename[:-3]}"
                    try:
                        await bot.load_extension(extension)
                        logger.info(f"{extension} chargé avec succès.")
                    except Exception as e:
                        logger.exception(f"Erreur lors du chargement de {extension}: {e}")

@bot.event
async def on_ready():
    logger.info(f"{bot.user} est connecté avec succès.")
    await bot.tree.sync()

@bot.event
async def on_error(event, *args, **kwargs):
    logger.exception(f"Erreur non capturée dans l'événement {event}: {args} {kwargs}")

async def main():
    async with bot:
        await load_all_cogs()
        # Si vous avez un request_manager:
        # from cogs.utilities.request_manager import setup_request_manager
        # setup_request_manager(bot)
        await bot.start(DISCORD_BOT_TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot arrêté manuellement.")
