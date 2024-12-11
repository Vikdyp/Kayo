import discord
from discord.ext import commands
import logging
import logging.config
import os
from dotenv import load_dotenv
import asyncio
from config_log import LOGGING_ENABLED, GLOBAL_DEBUG  # Assurez-vous que c'est bien config_log.py

# Charger les variables d'environnement
load_dotenv()

# Configuration centralisée des logs
def setup_logging():
    log_level_bot = logging.DEBUG if LOGGING_ENABLED.get("bot", False) and GLOBAL_DEBUG else logging.CRITICAL
    log_level_request_manager = logging.DEBUG if LOGGING_ENABLED.get("request_manager", False) and GLOBAL_DEBUG else logging.CRITICAL
    log_level_configuration_channels = logging.DEBUG if LOGGING_ENABLED.get("configuration.channels", False) and GLOBAL_DEBUG else logging.CRITICAL

    logging_config = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'standard': {
                'format': "\n%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            },
        },
        'handlers': {
            'file_bot': {
                'level': 'DEBUG' if LOGGING_ENABLED.get("bot", False) and GLOBAL_DEBUG else 'CRITICAL',
                'class': 'logging.FileHandler',
                'formatter': 'standard',
                'filename': 'logs/bot.log',
                'encoding': 'utf-8',
                'mode': 'a',
            },
            'console': {
                'level': 'DEBUG' if LOGGING_ENABLED.get("bot", False) and GLOBAL_DEBUG else 'CRITICAL',
                'class': 'logging.StreamHandler',
                'formatter': 'standard',
            },
        },
        'loggers': {
            'bot': {
                'handlers': ['file_bot', 'console'],
                'level': log_level_bot,
                'propagate': False,
            },
            'request_manager': {
                'handlers': ['file_bot'],
                'level': log_level_request_manager,
                'propagate': False,
            },
            'configuration.channels': {  # Exemple pour un cog
                'handlers': ['file_bot'],
                'level': log_level_configuration_channels,
                'propagate': False,
            },
            # Ajoutez d'autres loggers pour vos cogs si nécessaire
        }
    }

    logging.config.dictConfig(logging_config)

# Initialiser la configuration des logs
setup_logging()
logger = logging.getLogger('bot')

intents = discord.Intents.default()
intents.members = True
intents.voice_states = True
intents.guilds = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, description="Bot complet")

# Charger les tokens depuis les variables d'environnement
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
VALORANT_API_KEY = os.getenv("VALORANT_API_KEY")

if not DISCORD_BOT_TOKEN:
    logger.critical("Le token du bot n'est pas défini. Veuillez vérifier le fichier .env.")
    exit(1)

if not VALORANT_API_KEY:
    logger.critical("La clé API Valorant n'est pas définie. Veuillez vérifier le fichier .env.")
    exit(1)

# Assigner la clé API Valorant à l'objet Bot
bot.valorant_api_key = VALORANT_API_KEY

async def load_all_cogs():
    cogs_folders = [
        "configuration", "economy", "moderation", 
        "ranking", "reputation", "role_management", 
        "scrims", "tournaments", "voice_management"
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
                        logger.exception(f"Erreur lors du chargement de {extension}: {e}")
    
    from cogs.utilities.request_manager import setup_request_manager
    setup_request_manager(bot)

    from cogs.voice_management.online_count_updater import setup_online_count_updater
    setup_online_count_updater(bot)

@bot.event
async def on_ready():
    logger.info(f"{bot.user} est connecté avec succès.")
    await bot.tree.sync()

@bot.event
async def on_error(event, *args, **kwargs):
    logger.exception(f"Erreur non capturée dans l'événement {event}: {args} {kwargs}")

async def shutdown(bot):
    logger.info("Arrêt propre du bot...")
    for task in asyncio.all_tasks():
        if task is not asyncio.current_task():
            task.cancel()
    await bot.close()

async def main():
    async with bot:
        await load_all_cogs()
        await bot.start(DISCORD_BOT_TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interruption par l'utilisateur. Arrêt...")
        asyncio.run(shutdown(bot))
    except Exception as e:
        logger.exception(f"Erreur inattendue : {e}")
    finally:
        logger.info("Le bot est maintenant arrêté.")
