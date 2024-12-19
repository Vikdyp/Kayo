import discord
from discord.ext import commands, tasks
import logging
import asyncio
import os
from config import DISCORD_TOKEN, TEST_GUILD_ID, LOGGING, TEST_MODE
from utils.database import database
from utils.request_manager import setup_request_manager, teardown_request_manager
from cogs.voice_management.online_count_updater import setup_rank_updater, teardown_rank_updater, rank_updater

def configure_logging():
    """Configure le niveau de logging pour chaque module."""
    # Supprimer les handlers par défaut
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    # Configurer chaque logger
    for logger_name, is_enabled in LOGGING.items():
        logger = logging.getLogger(logger_name)
        if is_enabled:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.CRITICAL)

    # Ajout d'un FileHandler global pour conserver l'historique des logs
    file_handler = logging.FileHandler('bot.log', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    logging.getLogger().addHandler(file_handler)

    # Ajout d'un StreamHandler pour voir les logs en console
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.DEBUG)
    stream_handler.setFormatter(formatter)
    logging.getLogger().addHandler(stream_handler)

configure_logging()

intents = discord.Intents.all()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

cog_paths = [
    'cogs.configuration.channels_configuration',
    'cogs.configuration.role_mappings_configuration',
    'cogs.moderation.clean',
    'cogs.admin.admin',
]

@bot.event
async def on_ready():
    logger = logging.getLogger('bot')
    logger.info(f'Connecté en tant que {bot.user}')

    await database.connect()
    database.set_bot_reference(bot)
    setup_request_manager(bot)
    logger.info("RequestManager démarré.")

    # Tâche de nettoyage des logs planifiée
    if not clean_old_logs.is_running():
        clean_old_logs.start()
        logger.info("Tâche de nettoyage planifiée démarrée.")

    # Tâche de mise à jour des salons
    if not rank_updater.task or not rank_updater.task.is_running():
        setup_rank_updater(bot)
        logger.info("Tâche de mise à jour des salons démarrée.")

    # Synchronisation des commandes
    await asyncio.sleep(1)
    try:
        if TEST_MODE:
            guild = discord.Object(id=int(TEST_GUILD_ID))
            synced_commands = await bot.tree.sync(guild=guild)
            logger.info(f"Commandes synchronisées pour la guilde {TEST_GUILD_ID}: {len(synced_commands)}")
        else:
            synced_commands = await bot.tree.sync()
            logger.info(f"Commandes globales synchronisées : {len(synced_commands)}")
    except Exception as e:
        logger.error(f"Erreur lors de la synchronisation des commandes : {e}")

@bot.event
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    """Handler global pour les erreurs de slash commands."""
    logger = logging.getLogger('bot')
    logger.error(f"Erreur dans une commande slash : {error}")
    try:
        await interaction.response.send_message("Une erreur interne est survenue.", ephemeral=True)
    except:
        pass

@tasks.loop(hours=24)
async def clean_old_logs():
    logger = logging.getLogger('bot')
    try:
        await database.purge_old_logs_and_clean_relations(days=30)
    except Exception as e:
        logger.error(f"Erreur lors du nettoyage automatique des logs : {e}")

@bot.event
async def on_disconnect():
    logger = logging.getLogger('bot')
    logger.warning("Bot déconnecté de Discord. Le bot tentera de se reconnecter automatiquement...")
    # Ne pas déconnecter la base de données. `ensure_connected()` s'occupera de la reconnexion si besoin.
    # Pas besoin non plus de redémarrer une surveillance spéciale.

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
    logger = logging.getLogger('bot')
    try:
        async with bot:
            await load_cogs()
            await bot.start(DISCORD_TOKEN)
    except KeyboardInterrupt:
        logger.info("Bot arrêté manuellement.")
    except Exception as e:
        logger.exception(f"Erreur inattendue: {e}")
    finally:
        # A l'arrêt du bot, déconnexion propre de la DB et arrêt du RequestManager
        await database.disconnect()
        teardown_request_manager()
        logger.info("Bot arrêté proprement.")

if __name__ == '__main__':
    asyncio.run(main())
