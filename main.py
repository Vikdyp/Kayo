import discord
from discord.ext import commands
import asyncio
import os
import logging
from dotenv import load_dotenv
from typing import Optional, List, Dict, Set
from pathlib import Path
import importlib.util

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

def find_cogs(cogs_directory: Path) -> List[Path]:
    """Trouve tous les fichiers de cogs dans le répertoire spécifié."""
    return list(cogs_directory.rglob("*.py"))

def load_cog_module(cog_path: Path) -> Optional[importlib.util.module_from_spec]:
    """Charge un module de cog sans l'exécuter."""
    spec = importlib.util.spec_from_file_location(cog_path.stem, cog_path)
    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
            return module
        except Exception as e:
            logger.exception(f"Erreur lors de l'importation du module {cog_path}: {e}")
            return None
    return None

def build_dependency_graph(cog_modules: Dict[str, importlib.util.module_from_spec]) -> Dict[str, Set[str]]:
    """
    Construire un graphe de dépendances où chaque clé est un cog et les valeurs sont les cogs dont il dépend.
    """
    dependency_graph = {}
    for cog_name, module in cog_modules.items():
        dependencies = getattr(module, 'dependencies', [])
        # Filtrer les dépendances vides
        dependencies = [dep for dep in dependencies if dep]
        dependency_graph[cog_name] = set(dependencies)
    return dependency_graph

def topological_sort(dependency_graph: Dict[str, Set[str]]) -> List[str]:
    """
    Effectue un tri topologique sur le graphe de dépendances.
    Retourne une liste ordonnée de cogs à charger.
    """
    from collections import defaultdict, deque

    in_degree = defaultdict(int)
    graph = defaultdict(list)

    # Construire le graphe et compter les degrés entrants
    for cog, deps in dependency_graph.items():
        for dep in deps:
            graph[dep].append(cog)
            in_degree[cog] += 1

    # Trouver tous les cogs avec un degré entrant de 0
    queue = deque([cog for cog in dependency_graph if in_degree[cog] == 0])
    sorted_order = []

    while queue:
        current = queue.popleft()
        sorted_order.append(current)

        for neighbor in graph[current]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(sorted_order) != len(dependency_graph):
        # Il y a un cycle ou des dépendances manquantes
        unresolved = set(dependency_graph.keys()) - set(sorted_order)
        raise Exception(f"Il y a des cycles de dépendances ou des dépendances manquantes parmi les cogs : {unresolved}")

    return sorted_order

async def load_and_sync_all_cogs():
    """Charge tous les cogs depuis le répertoire 'cogs' en respectant les dépendances et synchronise les commandes."""
    logger.info("Chargement de tous les cogs avec gestion des dépendances...")
    cogs_dir = Path("./cogs")
    cog_files = find_cogs(cogs_dir)

    # Charger les modules de cogs et collecter leurs dépendances
    cog_modules = {}
    cog_paths = {}
    for cog_file in cog_files:
        if cog_file.name.startswith("__"):
            continue
        # Ignorer les modules utilitaires
        if cog_file.parent.name == "utilities":
            continue
        module = load_cog_module(cog_file)
        if module:
            # Correction ici
            cog_name = f"cogs.{cog_file.relative_to(cogs_dir).with_suffix('').as_posix().replace('/', '.')}"
            cog_modules[cog_name] = module
            cog_paths[cog_name] = cog_file

    # Construire le graphe de dépendances
    dependency_graph = build_dependency_graph(cog_modules)

    try:
        load_order = topological_sort(dependency_graph)
        logger.info(f"Ordre de chargement des cogs: {load_order}")
    except Exception as e:
        logger.critical(f"Erreur lors du tri des cogs: {e}")
        return

    # Charger les cogs dans l'ordre déterminé
    for cog_name in load_order:
        cog_file = cog_paths.get(cog_name)
        if cog_file:
            try:
                await bot.load_extension(cog_name)
                logger.info(f"{cog_name} chargé avec succès.")
            except commands.errors.ExtensionAlreadyLoaded:
                logger.warning(f"{cog_name} est déjà chargé.")
            except commands.errors.NoEntryPointError:
                logger.error(f"{cog_name} n'a pas de fonction 'setup'.")
            except commands.errors.ExtensionFailed as e:
                logger.error(f"Erreur lors du chargement de {cog_name}: {e}")
        else:
            logger.warning(f"Chemin du fichier pour {cog_name} non trouvé.")

    logger.info("Tous les cogs sont chargés avec succès.")
    await sync_all_commands()

@bot.event
async def on_ready():
    """Événement déclenché lorsque le bot est prêt."""
    logger.info(f"{bot.user} est connecté avec succès.")
    await load_and_sync_all_cogs()
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
