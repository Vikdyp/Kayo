# bot.py

import discord
from discord.ext import commands, tasks
import logging
import asyncio
import os
from config import DISCORD_TOKEN, TEST_GUILD_ID, LOGGING, TEST_MODE
from utils.database import database
from utils.checks import rules_check, rules_interaction_check
from cogs.other.online_count_updater import setup_rank_updater, teardown_rank_updater, rank_updater

def configure_logging():
    """Configure le niveau et le format des logs pour l'ensemble du projet."""

    logs_dir = "logs"
    os.makedirs(logs_dir, exist_ok=True)
    log_file = os.path.join(logs_dir, "bot.log")

    # Supprimer les handlers par défaut
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    # Configurer chaque logger
    for logger_name, is_enabled in LOGGING.items():
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.DEBUG if is_enabled else logging.CRITICAL)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    # Ajout d'un FileHandler global
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logging.getLogger().addHandler(file_handler)

    # Ajout d'un StreamHandler pour la console
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

# On crée le bot
bot = commands.Bot(command_prefix='!', intents=intents)
bot.check(rules_check())

@bot.tree.interaction_check
async def _global_rules_check(interaction: discord.Interaction) -> bool:
    return await rules_interaction_check(interaction)

# On attache un logger "bot" à l'instance
logger = logging.getLogger('bot')
bot.logger = logger  # <-- Correction pour éviter l'erreur 'Bot' object has no attribute 'logger'

cog_paths = [
    'cogs.configuration.channels_configuration',
    'cogs.configuration.role_mappings_configuration',
    'cogs.moderation.clean',
    'cogs.admin.admin',
    'cogs.moderation.moderation',
    #'cogs.file_counter.file_counter',
    'cogs.accueil.accueil',
    'cogs.role_management.game_role',
    'cogs.ranking.assign_rank',
    'cogs.rules.rules',
    'cogs.moderation.unban_requests',
    'cogs.troll.quoicoubeh',
    # 'cogs.role_management.auto_role',
    # 'cogs.role_management.language_role',
    'cogs.voice_management.queue_cog',
    'cogs.voice_management.team_cog',
    'cogs.voice_management.voice_cleaner',
    'cogs.accueil.stalker',
    #'SQL_test', #TEST
    'cogs.reputation.reputation',
    #'cogs.other.test',
    'cogs.other.vocal_creator',
    'cogs.scrims.scrims',
    'cogs.other.rank_up',
    #'cogs.other.invite_tracker',  ACTIVER SI EVENT EN COURS
    #'cogs.other.event',           ACTIVER SI EVENT EN COURS
    #'cogs.tournaments.tournament',
    'cogs.admin.status',
    'cogs.twitch.twitch_notifier',
    'cogs.ranking.mmr_tracker',
]

@bot.event
async def on_ready():
    logger.info(f'Connecté en tant que {bot.user}')

    await database.connect()
    database.set_bot_reference(bot)

    if not clean_old_logs.is_running():
        clean_old_logs.start()
        logger.info("Tâche de nettoyage planifiée démarrée.")

    if not rank_updater.task or not rank_updater.task.is_running():
        setup_rank_updater(bot)
        logger.info("Tâche de mise à jour des salons démarrée.")

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
    logger.warning("Bot déconnecté de Discord. Reconnexion automatique possible...")

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
        await database.disconnect()
        logger.info("Bot arrêté proprement.")

if __name__ == '__main__':
    asyncio.run(main())
