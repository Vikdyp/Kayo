import discord
from discord.ext import commands
import asyncio
import os
import logging
from dotenv import load_dotenv
from typing import Optional, List
from pathlib import Path

# Charger les variables d'environnement depuis le fichier .env
load_dotenv()

# Configuration des logs
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

logger = logging.getLogger('discord.Main')

# Ligne de séparation pour démarquer les sections
def log_separator(title: str):
    separator = "=" * 50
    logger.info(f"\n{separator}\n{title}\n{separator}")

# Définition des intents nécessaires
intents = discord.Intents.default()
intents.members = True
intents.voice_states = True
intents.guilds = True
intents.message_content = True  # Assurez-vous que ceci est activé

# Initialisation du bot avec les intents et une description
bot = commands.Bot(
    command_prefix="!",
    description="Bot de gestion des salons vocaux, des rapports et des rôles",
    intents=intents
)

# Charger les variables d'environnement avec vérifications
try:
    DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    AUTHORIZED_USER_ID = int(os.getenv("AUTHORIZED_USER_ID"))
    NOTIFY_USERS = [int(uid.strip()) for uid in os.getenv("NOTIFY_USERS", "").split(",") if uid.strip()]
    VALORANT_API_KEY = os.getenv("VALORANT_API_KEY")  # Charger la clé API Valorant
except (TypeError, ValueError) as e:
    logger.error(f"Erreur lors du chargement des variables d'environnement: {e}")
    raise

# Validation des configurations essentielles
if not DISCORD_BOT_TOKEN:
    logger.critical("Le token du bot n'est pas défini. Veuillez vérifier le fichier .env.")
    raise ValueError("Le token du bot n'est pas défini.")

# Définir l'attribut valorant_api_key sur le bot
bot.valorant_api_key = VALORANT_API_KEY
if not bot.valorant_api_key:
    logger.warning("VALORANT_API_KEY n'est pas défini. Certaines fonctionnalités pourraient ne pas fonctionner.")

async def notify_users_on_ready():
    """Envoie une notification aux utilisateurs spécifiés lorsque le bot est prêt."""
    await bot.wait_until_ready()
    guild: discord.Guild = bot.guilds[0] if bot.guilds else None
    if not guild:
        logger.warning("Aucun serveur trouvé pour envoyer les notifications.")
        return

    log_separator("Envoi des notifications")
    for user_id in NOTIFY_USERS:
        user: Optional[discord.Member] = guild.get_member(user_id)
        if user:
            try:
                await user.send("Le bot est maintenant connecté et prêt à fonctionner.")
                logger.info(f"Message de notification envoyé à {user.name}.")
            except discord.errors.HTTPException as e:
                logger.error(f"Erreur HTTP lors de l'envoi du message à {user.name}: {e}")
            except discord.errors.Forbidden:
                logger.error(f"Permission refusée pour envoyer un message à {user.name}.")
        else:
            logger.warning(f"L'utilisateur avec l'ID {user_id} n'a pas été trouvé dans le serveur.")

async def sync_all_commands(interaction: Optional[discord.Interaction] = None):
    """Synchronise toutes les commandes du bot avec Discord."""
    log_separator("Synchronisation des commandes")
    try:
        synced = await bot.tree.sync()
        if interaction:
            await interaction.followup.send(f"Synced {len(synced)} command(s).", ephemeral=True)
        else:
            logger.info(f"Synced {len(synced)} command(s).")
    except discord.errors.HTTPException as e:
        if interaction:
            await interaction.followup.send(f"Failed to sync commands: {e}", ephemeral=True)
        logger.error(f"Failed to sync commands: {e}")

def find_cogs(cogs_directory: Path) -> List[Path]:
    """Trouve tous les fichiers de cogs dans le répertoire spécifié."""
    return list(cogs_directory.rglob("*.py"))

async def load_all_cogs():
    """Charge tous les cogs depuis le répertoire 'cogs'."""
    log_separator("Chargement des cogs")
    cogs_dir = Path("./cogs")
    cog_files = find_cogs(cogs_dir)

    for cog_file in cog_files:
        if cog_file.name.startswith("__") or cog_file.parent.name == "utilities":
            continue

        cog_name = f"cogs.{cog_file.relative_to(cogs_dir).with_suffix('').as_posix().replace('/', '.')}"
        if cog_name in bot.extensions:  # Vérifier si déjà chargé
            logger.warning(f"{cog_name} est déjà chargé.")
            continue

        try:
            await bot.load_extension(cog_name)
            logger.info(f"{cog_name} chargé avec succès.")
        except commands.errors.ExtensionAlreadyLoaded:
            logger.warning(f"{cog_name} est déjà chargé.")
        except commands.errors.NoEntryPointError:
            logger.error(f"{cog_name} n'a pas de fonction 'setup'.")
        except commands.errors.ExtensionFailed as e:
            logger.error(f"Erreur lors du chargement de {cog_name}: {e}")

    logger.info("Tous les cogs sont chargés avec succès.")
    await sync_all_commands()

@bot.event
async def on_ready():
    """Événement déclenché lorsque le bot est prêt."""
    log_separator("Bot prêt")
    logger.info(f"{bot.user} est connecté avec succès.")
    await load_all_cogs()
    await notify_users_on_ready()

@bot.tree.command(name="sync_all", description="Synchroniser toutes les commandes")
async def sync_all_command(interaction: discord.Interaction):
    """
    Commande pour synchroniser toutes les commandes du bot avec Discord.

    Parameters:
        interaction (discord.Interaction): L'interaction de l'utilisateur.
    """
    if interaction.user.id == AUTHORIZED_USER_ID:
        await interaction.response.defer(ephemeral=True)
        await load_all_cogs()
        await interaction.followup.send("Toutes les commandes ont été synchronisées avec succès.", ephemeral=True)
        logger.info(f"Commande /sync_all utilisée par {interaction.user}.")
    else:
        await interaction.response.send_message("Vous n'avez pas la permission d'utiliser cette commande.", ephemeral=True)
        logger.warning(f"Utilisateur {interaction.user} a tenté d'utiliser /sync_all sans autorisation.")

@bot.event
async def on_error(event_method: str, *args, **kwargs):
    """Gère les erreurs non capturées dans les événements."""
    logger.exception(f"Erreur dans l'événement {event_method}: {args} {kwargs}")

async def main():
    """Fonction principale pour démarrer le bot."""
    async with bot:
        await bot.start(DISCORD_BOT_TOKEN)

if __name__ == "__main__":
    try:
        log_separator("Démarrage du bot")
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot arrêté manuellement.")
