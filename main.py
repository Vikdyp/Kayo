# main.py

import discord
from discord.ext import commands
import asyncio
import os
import logging
from dotenv import load_dotenv
from typing import Optional

# Charger les variables d'environnement depuis le fichier .env
load_dotenv()

# Configuration des logs
if not os.path.exists('logs'):
    os.makedirs('logs')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s:%(levelname)s:%(name)s: %(message)s",
    handlers=[
        logging.FileHandler(filename='logs/bot.log', encoding='utf-8', mode='a'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger('discord.Main')

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
    NOTIFY_USERS = [int(uid.strip()) for uid in os.getenv("NOTIFY_USERS").split(",") if uid.strip()]
except (TypeError, ValueError) as e:
    logger.error(f"Erreur lors du chargement des variables d'environnement: {e}")
    raise

# Validation des configurations essentielles
if not DISCORD_BOT_TOKEN:
    logger.critical("Le token du bot n'est pas défini. Veuillez vérifier le fichier .env.")
    raise ValueError("Le token du bot n'est pas défini.")

async def notify_users_on_ready():
    """Envoie une notification aux utilisateurs spécifiés lorsque le bot est prêt."""
    await bot.wait_until_ready()
    guild: discord.Guild = bot.guilds[0] if bot.guilds else None
    if not guild:
        logger.warning("Aucun serveur trouvé pour envoyer les notifications.")
        return

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

async def sync_all_commands(interaction: discord.Interaction = None):
    """Synchronise toutes les commandes du bot avec Discord."""
    logger.info("Début de la synchronisation de toutes les commandes...")
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

@bot.event
async def on_ready():
    """Événement déclenché lorsque le bot est prêt."""
    logger.info(f"{bot.user} est connecté avec succès.")
    await load_and_sync_all_cogs()
    await notify_users_on_ready()

async def load_and_sync_all_cogs():
    """Charge tous les cogs depuis le répertoire 'cogs' et synchronise les commandes."""
    logger.info("Chargement de tous les cogs...")
    cogs_dir = "./cogs"
    for root, dirs, files in os.walk(cogs_dir):
        for filename in files:
            if filename.endswith(".py") and not filename.startswith("__"):
                cog_path = os.path.join(root, filename)
                module_path = cog_path.replace("/", ".").replace("\\", ".")[:-3]  # Retirer .py
                try:
                    await bot.load_extension(module_path)
                    logger.info(f"{module_path} chargé avec succès.")
                except Exception as e:
                    logger.error(f"Erreur lors du chargement de {module_path}: {e}")
    logger.info("Tous les cogs sont chargés.")
    await sync_all_commands()

@bot.tree.command(name="sync_all", description="Synchroniser toutes les commandes")
async def sync_all(interaction: discord.Interaction):
    """
    Commande pour synchroniser toutes les commandes du bot avec Discord.

    Parameters:
        interaction (discord.Interaction): L'interaction de l'utilisateur.
    """
    if interaction.user.id == AUTHORIZED_USER_ID:
        await interaction.response.defer(ephemeral=True)
        await load_and_sync_all_cogs()
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
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot arrêté manuellement.")
    except Exception as e:
        logger.critical(f"Erreur critique lors du démarrage du bot: {e}")
