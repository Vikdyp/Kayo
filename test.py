import typing
import discord
from discord.ext import commands
import logging
import os
from dotenv import load_dotenv
import asyncio
import aiohttp
print("aiohttp")
print(aiohttp.__version__)
print("discord")
print(discord.__version__)
print(f"Module 'discord' importé depuis : {discord.__file__}")
print(f"Répertoire de travail actuel : {os.getcwd()}")

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
    # Liste des dossiers contenant les cogs
    cogs_folders = [
        "test"
    ]
    
    for folder in cogs_folders:
        cogs_dir = os.path.join("cogs", folder)
        if os.path.exists(cogs_dir):
            for filename in os.listdir(cogs_dir):
                if filename.endswith(".py") and filename != "__init__.py":
                    extension = f"cogs.{folder}.{filename[:-3]}"
                    try:
                        await bot.load_extension(extension)
                        logger.info(f"{extension} chargé avec succès.")
                    except Exception as e:
                        logger.error(f"Erreur lors du chargement de {extension}: {e}")
                        logger.exception(e)
                        # Arrête le chargement si un cog échoue
                        raise RuntimeError(f"Arrêt du chargement à cause de {extension}")

@bot.event
async def on_ready():
    logger.info(f"{bot.user} est connecté avec succès.")
    await bot.tree.sync()

@bot.event
async def on_error(event, *args, **kwargs):
    logger.exception(f"Erreur non capturée dans l'événement {event}: {args} {kwargs}")

async def main():
    async with bot:
        try:
            await load_all_cogs()
        except RuntimeError as e:
            logger.critical(f"Erreur critique lors du chargement des cogs : {e}")
            return
        await bot.start(DISCORD_BOT_TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot arrêté manuellement.")
