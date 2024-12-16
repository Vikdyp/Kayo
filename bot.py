import discord
from discord.ext import commands, tasks
import logging
from utils.database import database
from config import DISCORD_TOKEN, TEST_GUILD_ID, LOGGING, TEST_MODE
import asyncio
from utils.request_manager import setup_request_manager, teardown_request_manager
from cogs.voice_management.online_count_updater import setup_rank_updater, teardown_rank_updater, rank_updater

def configure_logging():
    """Configure le niveau de logging pour chaque module en fonction du fichier de configuration."""
    # Supprimer les handlers de base
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    # Configurer chaque logger en fonction de `LOGGING`
    for logger_name, is_enabled in LOGGING.items():
        logger = logging.getLogger(logger_name)
        if is_enabled:
            logger.setLevel(logging.DEBUG)  # Activer les logs (DEBUG par exemple)
            handler = logging.StreamHandler()  # Handler pour afficher dans la console
            handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            logger.addHandler(handler)
        else:
            logger.setLevel(logging.CRITICAL)  # Désactiver les logs (CRITICAL = quasi muet)

# Appeler configure_logging avant tout
configure_logging()

# Configuration des intents
intents = discord.Intents.all()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True

# Initialisation du bot
bot = commands.Bot(command_prefix='!', intents=intents)

# Liste explicite des cogs à charger
cog_paths = [
    'cogs.configuration.channels_configuration',
    'cogs.configuration.role_mappings_configuration',
    'cogs.moderation.clean',
]

@bot.event
async def on_ready():
    logger = logging.getLogger('bot')
    logger.info(f'Connecté en tant que {bot.user}')

    await database.connect()
    monitor_database.start()  # Démarrer la surveillance de la connexion
    logger.info("Surveillance de la connexion à la base de données démarrée.")

    setup_request_manager(bot)
    logger.info("RequestManager démarré.")

    # Démarrer les tâches planifiées
    if not clean_old_logs.is_running():
        clean_old_logs.start()
        logger.info("Tâche de nettoyage planifiée démarrée.")

    # Démarrer le RankUpdater
    if not rank_updater.task or not rank_updater.task.is_running():
        setup_rank_updater(bot)
        logger.info("Tâche de mise à jour des salons démarrée.")

    # Synchroniser les commandes
    await asyncio.sleep(1)  # Facultatif
    try:
        if TEST_MODE:
            # Mode test : synchroniser uniquement avec TEST_GUILD_ID
            guild = discord.Object(id=int(TEST_GUILD_ID))
            synced_commands = await bot.tree.sync(guild=guild)
            logger.info(f"Commandes synchronisées pour la guilde {TEST_GUILD_ID}: {len(synced_commands)}")
        else:
            # Mode normal : synchroniser globalement
            synced_commands = await bot.tree.sync()
            logger.info(f"Commandes globales synchronisées : {len(synced_commands)}")
    except Exception as e:
        logger.error(f"Erreur lors de la synchronisation des commandes : {e}")

@tasks.loop(hours=24)
async def clean_old_logs():
    logger = logging.getLogger('bot')
    try:
        await database.purge_old_logs_and_clean_relations(days=30)
    except Exception as e:
        logger.error(f"Erreur lors du nettoyage automatique des logs : {e}")

@tasks.loop(hours=1)
async def monitor_database():
    """Vérifie la connexion à la base de données toutes les heures."""
    logger = logging.getLogger('bot')
    try:
        await database.ensure_connected()
        logger.info("Connexion à la base de données vérifiée avec succès.")
    except Exception as e:
        logger.error(f"Erreur lors de la vérification de la connexion à la base de données : {e}")

def start_monitor_database():
    """Démarre la tâche `monitor_database` si elle n'est pas déjà en cours."""
    if not monitor_database.is_running():
        monitor_database.start()
        logger = logging.getLogger('bot')
        logger.info("Tâche `monitor_database` démarrée.")

@bot.event
async def on_disconnect():
    logger = logging.getLogger('bot')
    teardown_request_manager()
    await database.disconnect()
    logger.info("Déconnecté et déconnecté de la base de données.")

async def load_cogs():
    logger = logging.getLogger('bot')
    for cog_path in cog_paths:
        try:
            await bot.load_extension(cog_path)
            logger.info(f'Cog chargé: {cog_path}')
        except commands.errors.ExtensionAlreadyLoaded:
            logger.warning(f'Cog déjà chargé: {cog_path}')
        except commands.errors.ExtensionNotFound:
            logger.error(f'Cog non trouvé: {cog_path}')
        except commands.errors.NoEntryPointError:
            logger.error(f'Pas de fonction setup dans le cog: {cog_path}')
        except Exception as e:
            logger.exception(f'Erreur lors du chargement du cog {cog_path}: {e}')

async def main():
    async with bot:
        await load_cogs()
        await bot.start(DISCORD_TOKEN)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger = logging.getLogger('bot')
        logger.info("Bot arrêté manuellement.")
    except Exception as e:
        logger = logging.getLogger('bot')
        logger.exception(f"Erreur inattendue: {e}")
    finally:
        loop = asyncio.get_event_loop()
        if not loop.is_closed():
            loop.run_until_complete(database.disconnect())
            teardown_request_manager()
            loop.close()
        logger.info("Bot arrêté proprement.")
