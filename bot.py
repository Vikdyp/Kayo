# bot.py
import logging
import asyncio
import discord
from discord.ext import commands, tasks

from logging_config import setup_logging
from config import DISCORD_TOKEN, TEST_GUILD_ID, LOG_LEVELS, TEST_MODE
from utils.database import database
from utils.checks import rules_check, rules_interaction_check
from cogs.other.online_count_updater import setup_rank_updater

# Configure le logging au démarrage
setup_logging(LOG_LEVELS)

logger = logging.getLogger("bot")

intents = discord.Intents.all()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Si rules_check() renvoie une fonction predicate, OK.
# Sinon, la version standard est: bot.add_check(predicate)
bot.check(rules_check())

@bot.tree.interaction_check
async def _global_rules_check(interaction: discord.Interaction) -> bool:
    return await rules_interaction_check(interaction)

cog_paths = [
    "cogs.configuration.channels_configuration",
    "cogs.configuration.role_mappings_configuration",
    "cogs.moderation.clean",
    "cogs.admin.admin",
    "cogs.moderation.moderation",
    "cogs.moderation.automod",
    "cogs.accueil.accueil",
    "cogs.role_management.game_role",
    "cogs.ranking.assign_rank",
    "cogs.rules.rules",
    "cogs.moderation.unban_requests",
    "cogs.troll.quoicoubeh",
    "cogs.voice_management.queue_cog",
    "cogs.voice_management.team_cog",
    "cogs.voice_management.voice_cleaner",
    "cogs.accueil.stalker",
    "cogs.reputation.reputation",
    "cogs.other.vocal_creator",
    "cogs.scrims.scrims",
    "cogs.other.rank_up",
    "cogs.admin.status",
    "cogs.twitch.twitch_notifier",
    "cogs.ranking.mmr_tracker",
    "cogs.shop.shop_notifier",
]

@bot.event
async def on_ready():
    logger.info("Connecté en tant que %s", bot.user)

    # Note: database.connect() est appelé dans main() avant le chargement des cogs
    database.set_bot_reference(bot)

    if not clean_old_logs.is_running():
        clean_old_logs.start()
        logger.info("Tâche de nettoyage planifiée démarrée.")

    setup_rank_updater(bot)
    logger.info("RankUpdater activé.")

    # Sync commandes
    await asyncio.sleep(1)
    try:
        if TEST_MODE:
            if not TEST_GUILD_ID:
                logger.error("TEST_MODE activé mais TEST_GUILD_ID manquant; sync ignorée.")
                return
            guild_id = int(TEST_GUILD_ID)
            guild = discord.Object(id=guild_id)
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            logger.info("Synced commandes test guild %s: %s", guild_id, len(synced))
        else:
            synced = await bot.tree.sync()
            logger.info("Synced commandes globales: %s", len(synced))
    except Exception:
        logger.exception("Erreur lors de la synchronisation des commandes")

@bot.event
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    logger.exception("Erreur dans une commande slash: %s", error)
    try:
        await interaction.response.send_message("Une erreur interne est survenue.", ephemeral=True)
    except Exception:
        pass

@tasks.loop(hours=24)
async def clean_old_logs():
    try:
        await database.purge_old_logs_and_clean_relations(days=30)
    except Exception:
        logger.exception("Erreur lors du nettoyage automatique des logs")

async def load_cogs():
    for cog_path in cog_paths:
        try:
            await bot.load_extension(cog_path)
            logger.info("Cog chargé: %s", cog_path)
        except commands.errors.ExtensionAlreadyLoaded:
            logger.warning("Cog déjà chargé: %s", cog_path)
        except commands.errors.ExtensionNotFound:
            logger.error("Cog non trouvé: %s", cog_path)
        except commands.errors.NoEntryPointError:
            logger.error("Pas de fonction setup dans le cog: %s", cog_path)
        except Exception:
            logger.exception("Erreur lors du chargement du cog %s", cog_path)

async def main():
    if not DISCORD_TOKEN:
        logger.error("DISCORD_TOKEN manquant (TEST_MODE=%s).", TEST_MODE)
        return

    try:
        # Connecter à la base de données AVANT de charger les cogs
        await database.connect()
        logger.info("Connexion à la base de données établie.")

        async with bot:
            await load_cogs()
            await bot.start(DISCORD_TOKEN)
    except KeyboardInterrupt:
        logger.info("Bot arrêté manuellement.")
    except Exception:
        logger.exception("Erreur inattendue")
    finally:
        await database.disconnect()
        logger.info("Bot arrêté proprement.")

if __name__ == "__main__":
    asyncio.run(main())
