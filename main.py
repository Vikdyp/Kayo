import discord
from discord.ext import commands
import asyncio
import os
import logging
from dotenv import load_dotenv

# Charger les variables d'environnement depuis le fichier .env
load_dotenv()

intents = discord.Intents.all()

bot = commands.Bot(command_prefix="!", description="Bot de gestion des salons vocaux et des rapports", intents=intents)

# Configuration des logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s:%(levelname)s:%(name)s: %(message)s",
    handlers=[
        logging.FileHandler(filename='logs/bot.log', encoding='utf-8', mode='a'),
        logging.StreamHandler()
    ]
)

AUTHORIZED_USER_ID = int(os.getenv("AUTHORIZED_USER_ID"))
NOTIFY_USERS = [int(uid) for uid in os.getenv("NOTIFY_USERS").split(",")]

async def notify_users_on_ready():
    guild = discord.utils.get(bot.guilds)
    if guild:
        for user_id in NOTIFY_USERS:
            user = guild.get_member(user_id)
            if user:
                try:
                    logging.info(f"Envoi du message de notification à {user.name}.")
                    await user.send("Le bot est maintenant connecté et prêt à fonctionner.")
                except discord.errors.HTTPException as e:
                    logging.error(f"Erreur HTTP lors de l'envoi du message à {user.name}: {e}")

async def sync_all_commands(interaction: discord.Interaction = None):
    logging.info("Début de la synchronisation de toutes les commandes...")
    try:
        synced = await bot.tree.sync()
        if interaction:
            await interaction.followup.send(f"Synced {len(synced)} command(s).", ephemeral=True)
        else:
            logging.info(f"Synced {len(synced)} command(s).")
    except discord.errors.HTTPException as e:
        if interaction:
            await interaction.followup.send(f"Failed to sync commands: {e}", ephemeral=True)
        else:
            logging.error(f"Failed to sync commands: {e}")

@bot.event
async def on_ready():
    logging.info(f"{bot.user.name} est connecté avec succès.")
    await load_and_sync_all_cogs()
    await notify_users_on_ready()

async def load_and_sync_all_cogs():
    logging.info("Chargement de tous les cogs...")
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py") and not filename.startswith("__"):
            cog = filename[:-3]
            try:
                await bot.load_extension(f"cogs.{cog}")
                logging.info(f"{cog} chargé avec succès.")
            except Exception as e:
                logging.error(f"Erreur lors du chargement de {cog}: {e}")
    logging.info("Tous les cogs sont chargés.")
    await sync_all_commands()

@bot.tree.command(name="sync_all", description="Synchroniser toutes les commandes")
async def sync_all(interaction: discord.Interaction):
    if interaction.user.id == AUTHORIZED_USER_ID:
        await interaction.response.defer(ephemeral=True)
        await load_and_sync_all_cogs()
        await interaction.followup.send("Toutes les commandes ont été synchronisées avec succès.", ephemeral=True)
    else:
        await interaction.response.send_message("Vous n'avez pas la permission d'utiliser cette commande.", ephemeral=True)

async def main():
    async with bot:
        discord_token = os.getenv("DISCORD_BOT_TOKEN")
        if discord_token:
            logging.info("Token trouvé.")
            await bot.start(discord_token)
        else:
            logging.error("Token du bot non trouvé. Assurez-vous qu'il est correctement défini dans le fichier .env.")

if __name__ == "__main__":
    asyncio.run(main())
