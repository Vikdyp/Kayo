# utils/database.py
from typing import Optional
import asyncpg
import logging
import asyncio
import os
import time

import discord
from config import DATABASE

logger = logging.getLogger("database")

class Database:
    """
    Classe gérant la connexion à la base de données via un pool asyncpg, et
    proposant différentes méthodes pour l'exécution de requêtes (fetch, execute, etc.).
    """

    def __init__(self):
        """
        Initialise la classe Database.
        """
        self.pool = None
        self.bot = None
        self.max_retries = 3
        self.retry_delay = 5

        # ID de salon Discord utilisé pour envoyer les logs en cas d'échec de reconnexion.
        self.log_channel_id = 1245888235604021348  # faux ID pour ne pas recevoir de message

        # Gestion des vérifications de connexion
        self._last_connection_check = 0       # Timestamp de la dernière vérification
        self._check_interval = 60            # Intervalle minimal (en secondes) entre deux vérifications

    def set_bot_reference(self, bot: discord.Client):
        """
        Associe une référence à l'instance du bot Discord
        afin d'envoyer éventuellement des logs sur un salon.
        """
        self.bot = bot

    async def connect(self):
        """
        Initialise un pool de connexion à la base de données.
        """
        try:
            self.pool = await asyncpg.create_pool(
                user=DATABASE['user'],
                password=DATABASE['password'],
                database=DATABASE['database'],
                host=DATABASE['host'],
                port=DATABASE['port'],
                ssl=DATABASE.get('ssl', False),
                min_size=1,
                max_size=20,
                max_inactive_connection_lifetime=600
            )
            logger.info("Connexion à la base de données réussie.")
        except Exception as e:
            logger.error(f"Erreur de connexion à la base de données : {e}")
            self.pool = None

    async def disconnect(self):
        """
        Ferme proprement le pool de connexions à la base de données.
        """
        if self.pool:
            await self.pool.close()
            self.pool = None
            logger.info("Déconnexion de la base de données.")

    async def ensure_connected(self):
        """
        Vérifie si la connexion au pool est toujours active.
        - Si self.pool est None, on tente une reconnexion.
        - Sinon, on ne refait le test de connexion (SELECT 1;) que si l'intervalle
          minimal depuis le dernier check est dépassé.
        """
        if self.pool is None:
            logger.warning("Le pool est None. Tentative de reconnexion...")
            await self.attempt_reconnect()
            return

        current_time = time.time()
        if current_time - self._last_connection_check < self._check_interval:
            return

        self._last_connection_check = current_time

        try:
            async with self.pool.acquire() as connection:
                await connection.execute('SELECT 1;')
        except (asyncpg.exceptions.ConnectionDoesNotExistError, asyncpg.exceptions.InterfaceError):
            logger.warning("La connexion au pool semble inactive. Tentative de reconnexion...")
            self._last_connection_check = 0
            await self.attempt_reconnect()
        except Exception as e:
            logger.error(f"Erreur inattendue lors de la vérification de la connexion : {e}")
            self._last_connection_check = 0
            await self.attempt_reconnect()
        else:
            logger.debug("Test de connexion réussi. Le pool est actif.")

    async def attempt_reconnect(self):
        """
        Tente de se reconnecter à la base de données jusqu'à max_retries,
        en laissant un délai de retry_delay entre chaque essai.
        """
        for attempt in range(1, self.max_retries + 1):
            await self.connect()
            if self.pool is not None:
                try:
                    async with self.pool.acquire() as connection:
                        await connection.execute('SELECT 1;')
                    logger.info(f"Reconnexion réussie après {attempt} tentative(s).")
                    self._last_connection_check = time.time()
                    return
                except Exception as e:
                    logger.error(f"Échec du test de connexion après reconnexion : {e}")
                    self.pool = None

            if attempt < self.max_retries:
                logger.warning(
                    f"Tentative de reconnexion {attempt} échouée. Nouvelle tentative dans {self.retry_delay}s."
                )
                await asyncio.sleep(self.retry_delay)

        logger.error(f"Impossible de rétablir la connexion après {self.max_retries} tentatives.")
        await self.send_logs_to_channel()

    async def send_logs_to_channel(self):
        """
        Envoie le fichier de logs ``logs/bot.log`` dans le channel Discord
        défini afin de pouvoir diagnostiquer l'erreur de connexion.
        """
        if not self.bot:
            logger.error("Impossible d'envoyer les logs : bot non défini dans database.")
            return

        channel = self.bot.get_channel(self.log_channel_id)
        if not channel:
            logger.error(f"Salon introuvable pour l'ID {self.log_channel_id}.")
            return

        log_path = os.path.join('logs', 'bot.log')
        if os.path.exists(log_path):
            try:
                await channel.send(
                    content="Échec de la reconnexion à la base de données. Voici les logs complets :",
                    file=discord.File(log_path)
                )
            except Exception as send_err:
                logger.error(f"Échec de l'envoi du fichier dans le salon : {send_err}")
        else:
            logger.error("Le fichier de logs 'logs/bot.log' est introuvable, impossible d'envoyer les logs.")

    async def execute(self, query: str, *args):
        """
        Exécute une requête SQL (INSERT, UPDATE, DELETE, etc.) sans retour particulier.
        Retourne le status de la requête (ex: 'INSERT 0 1') ou None en cas d'erreur.
        """
        await self.ensure_connected()
        if self.pool is None:
            logger.error("Impossible d'exécuter la requête: le pool est toujours None.")
            return None
        try:
            async with self.pool.acquire() as connection:
                return await connection.execute(query, *args)
        except Exception as e:
            logger.error(f"Erreur lors de l'exécution de la requête : {e}")
            return None

    async def fetch(self, query: str, *args):
        """
        Exécute une requête SQL (SELECT) et retourne plusieurs lignes.
        """
        await self.ensure_connected()
        if self.pool is None:
            logger.error("Impossible de fetch: le pool est toujours None.")
            return []
        try:
            async with self.pool.acquire() as connection:
                return await connection.fetch(query, *args)
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des données : {e}")
            return []

    async def fetchrow(self, query: str, *args):
        """
        Exécute une requête SQL (SELECT) et retourne la première ligne du résultat.
        """
        await self.ensure_connected()
        if self.pool is None:
            logger.error("Impossible de fetchrow: le pool est toujours None.")
            return None
        try:
            async with self.pool.acquire() as connection:
                return await connection.fetchrow(query, *args)
        except Exception as e:
            logger.error(f"Erreur lors de la récupération d'une ligne : {e}")
            return None

    async def fetchval(self, query: str, *args):
        """
        Exécute une requête SQL (SELECT) et retourne la première valeur de la première ligne.
        """
        await self.ensure_connected()
        if self.pool is None:
            logger.error("Impossible de fetchval: le pool est toujours None.")
            return None
        try:
            async with self.pool.acquire() as connection:
                return await connection.fetchval(query, *args)
        except Exception as e:
            logger.error(f"Erreur lors de la récupération d'une valeur : {e}")
            return None

    async def purge_old_logs_and_clean_relations(self, days=30):
        """
        Supprime les logs obsolètes (plus vieux que 'days' jours) dans la table `message_deletions`
        et nettoie les tables relationnelles (user_id, channel_id, serveur_id, nombre_id)
        uniquement si des logs existent.
        """
        # Supprime les anciennes entrées de logs
        await self.execute(f"DELETE FROM message_deletions WHERE timestamp < NOW() - INTERVAL '{days} days';")

        # Vérifie si des logs existent après suppression
        count_result = await self.fetchval("SELECT COUNT(*) FROM message_deletions;")
        count = int(count_result) if count_result is not None else 0

        if count > 0:
            clean_user_query = """
                DELETE FROM user_id
                WHERE id NOT IN (SELECT DISTINCT deleted_by FROM message_deletions)
                AND id NOT IN (SELECT DISTINCT target_user FROM message_deletions);
            """
            await self.execute(clean_user_query)

            clean_channel_query = """
                DELETE FROM channel_id
                WHERE id NOT IN (SELECT DISTINCT channel_id FROM message_deletions);
            """
            await self.execute(clean_channel_query)

            clean_server_query = """
                DELETE FROM serveur_id
                WHERE id NOT IN (SELECT DISTINCT guild_id FROM message_deletions);
            """
            await self.execute(clean_server_query)

            clean_number_query = """
                DELETE FROM nombre_id
                WHERE id NOT IN (SELECT DISTINCT message_count FROM message_deletions);
            """
            await self.execute(clean_number_query)

            logger.info("Logs obsolètes et données relationnelles non utilisées supprimés.")
        else:
            logger.info("Aucun log trouvé, nettoyage des relations non effectué.")

    async def get_or_create_id(self, table: str, column: str, value):
        """
        Récupère l'ID correspondant à 'value' dans la table/colonne indiquée,
        ou insère une nouvelle ligne si elle n'existe pas encore.
        """
        if not value:
            raise ValueError(f"La valeur pour {column} ne peut pas être vide.")

        try:
            query_select = f"SELECT id FROM {table} WHERE {column} = $1;"
            result = await self.fetchval(query_select, value)
            if result:
                logger.debug(f"ID trouvé pour {table}.{column} = {value}: {result}")
                return result

            query_insert = f"INSERT INTO {table} ({column}) VALUES ($1) RETURNING id;"
            result = await self.fetchval(query_insert, value)
            logger.debug(f"Nouvel ID créé pour {table}.{column} = {value}: {result}")
            return result
        except Exception as e:
            logger.error(f"Erreur SQL dans get_or_create_id pour {table}.{column} avec valeur '{value}': {e}")
            raise

    async def get_message_deletions(self, limit=50):
        """
        Récupère les dernières suppressions de messages (limit par défaut : 50).
        """
        query = """
            SELECT 
                md.id,
                u.discord_id AS deleted_by_user,
                ch.channel AS channel_name,
                s.serveur AS server_name,
                d.type AS deletion_type,
                tu.discord_id AS target_user,
                n.nombre AS message_count,
                md.timestamp
            FROM 
                message_deletions md
            LEFT JOIN user_id u ON md.deleted_by = u.id
            LEFT JOIN channel_id ch ON md.channel_id = ch.id
            LEFT JOIN serveur_id s ON md.guild_id = s.id
            LEFT JOIN deletion_id d ON md.deletion_type = d.id
            LEFT JOIN user_id tu ON md.target_user = tu.id
            LEFT JOIN nombre_id n ON md.message_count = n.id
            ORDER BY md.timestamp DESC
            LIMIT $1;
        """
        return await self.fetch(query, limit)

    async def log_message_deletion(
        self,
        deleted_by: int,     # ID Discord de l'utilisateur ayant supprimé
        channel: str,        # Nom du channel
        guild: str,          # Nom du serveur
        deletion_type: str,  # Type de suppression (ban, purge, etc.)
        target_user: Optional[int],  # ID Discord d'un utilisateur ciblé (ou None)
        message_count: int   # Nombre de messages supprimés
    ):
        """
        Enregistre une suppression de messages dans la table `message_deletions`.
        """
        try:
            # Récupérer ou créer les IDs nécessaires dans la base de données
            deleted_by_id = await self.get_or_create_id("user_id", "discord_id", deleted_by)
            channel_id = await self.get_or_create_id("channel_id", "channel", channel)
            guild_id = await self.get_or_create_id("serveur_id", "serveur", guild)
            deletion_type_id = await self.get_or_create_id("deletion_id", "type", deletion_type)
            target_user_id = None

            if target_user:
                target_user_id = await self.get_or_create_id("user_id", "discord_id", target_user)

            message_count_id = await self.get_or_create_id("nombre_id", "nombre", message_count)

            query = """
                INSERT INTO message_deletions (deleted_by, channel_id, guild_id, deletion_type, target_user, message_count)
                VALUES ($1, $2, $3, $4, $5, $6);
            """
            await self.execute(query, deleted_by_id, channel_id, guild_id, deletion_type_id, target_user_id, message_count_id)

            logger.info("Suppression de messages enregistrée dans la base de données.")
        except Exception as e:
            logger.error(f"Erreur lors de l'enregistrement de la suppression de messages : {e}")

# Instanciation globale (optionnelle, selon votre architecture)
database = Database()
