import asyncpg
import logging
import asyncio
import os
import discord
from config import DATABASE

logger = logging.getLogger("database")

class Database:
    def __init__(self):
        self.pool = None
        self.bot = None
        self.max_retries = 3
        self.retry_delay = 5
        self.log_channel_id = 1245888235604021348

    def set_bot_reference(self, bot: discord.Client):
        self.bot = bot

    async def connect(self):
        try:
            self.pool = await asyncpg.create_pool(
                user=DATABASE['user'],
                password=DATABASE['password'],
                database=DATABASE['database'],
                host=DATABASE['host'],
                port=DATABASE['port'],
                ssl=DATABASE.get('ssl', False),
                min_size=1,
                max_size=10,
                max_inactive_connection_lifetime=3600
            )
            logger.info("Connexion à la base de données réussie.")
        except Exception as e:
            logger.error(f"Erreur de connexion à la base de données : {e}")
            self.pool = None

    async def disconnect(self):
        if self.pool:
            await self.pool.close()
            self.pool = None
            logger.info("Déconnexion de la base de données.")

    async def ensure_connected(self):
        if self.pool is None:
            logger.warning("Le pool est None. Tentative de reconnexion...")
            await self.attempt_reconnect()
        else:
            try:
                async with self.pool.acquire() as connection:
                    await connection.execute('SELECT 1;')
            except (asyncpg.exceptions.ConnectionDoesNotExistError, asyncpg.exceptions.InterfaceError):
                logger.warning("La connexion au pool semble inactive. Tentative de reconnexion...")
                await self.attempt_reconnect()
            except Exception as e:
                logger.error(f"Erreur inattendue lors de la vérification de la connexion : {e}")
                await self.attempt_reconnect()
        logger.debug("ensure_connected terminé, pool prêt à être utilisé.")

    async def attempt_reconnect(self):
        for attempt in range(1, self.max_retries + 1):
            await self.connect()
            if self.pool is not None:
                # Tester immédiatement la connexion
                try:
                    async with self.pool.acquire() as connection:
                        await connection.execute('SELECT 1;')
                    logger.info(f"Reconnexion réussie après {attempt} tentative(s).")
                    return
                except Exception as e:
                    logger.error(f"Échec du test de connexion après reconnexion : {e}")
                    self.pool = None
            if attempt < self.max_retries:
                logger.warning(f"Tentative de reconnexion {attempt} échouée. Nouvelle tentative dans {self.retry_delay}s.")
                await asyncio.sleep(self.retry_delay)

        # Toutes les tentatives ont échoué
        logger.error(f"Impossible de rétablir la connexion après {self.max_retries} tentatives.")
        await self.send_logs_to_channel()

    async def send_logs_to_channel(self):
        if not self.bot:
            logger.error("Impossible d'envoyer les logs : bot non défini dans database.")
            return

        channel = self.bot.get_channel(self.log_channel_id)
        if not channel:
            logger.error(f"Salon introuvable pour l'ID {self.log_channel_id}.")
            return

        # Envoi du fichier de logs 'bot.log' généré par notre FileHandler
        if os.path.exists('bot.log'):
            try:
                await channel.send(
                    content="Échec de la reconnexion à la base de données. Voici les logs complets :",
                    file=discord.File('bot.log')
                )
            except Exception as send_err:
                logger.error(f"Échec de l'envoi du fichier dans le salon : {send_err}")
        else:
            logger.error("Le fichier de logs 'bot.log' est introuvable, impossible d'envoyer les logs.")

    async def execute(self, query, *args):
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

    async def fetch(self, query, *args):
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

    async def fetchrow(self, query, *args):
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

    async def fetchval(self, query, *args):
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
        await self.execute(f"DELETE FROM message_deletions WHERE timestamp < NOW() - INTERVAL '{days} days';")
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

    async def get_or_create_id(self, table, column, value):
        if not value:
            raise ValueError(f"La valeur pour {column} ne peut pas être vide.")

        try:
            query_select = f"SELECT id FROM {table} WHERE {column} = $1;"
            result = await self.fetchval(query_select, value)
            if result:
                return result
            query_insert = f"INSERT INTO {table} ({column}) VALUES ($1) RETURNING id;"
            return await self.fetchval(query_insert, value)
        except Exception as e:
            logger.error(f"Erreur SQL dans get_or_create_id pour {table}.{column} avec valeur '{value}': {e}")
            raise

    async def get_message_deletions(self, limit=50):
        query = """
            SELECT 
                md.id,
                u.username AS deleted_by_user,
                ch.channel AS channel_name,
                s.serveur AS server_name,
                d.type AS deletion_type,
                tu.username AS target_user,
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

database = Database()
