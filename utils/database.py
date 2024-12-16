# utils/database.py

import asyncpg
from config import DATABASE
import logging

logger = logging.getLogger("database")

class Database:
    def __init__(self):
        self.pool = None

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
            logging.info("Connexion à la base de données réussie.")
        except Exception as e:
            logging.error(f"Erreur de connexion à la base de données : {e}")

    async def disconnect(self):
        if self.pool:
            await self.pool.close()
            logging.info("Déconnexion de la base de données.")

    async def ensure_connected(self):
        """Vérifie si le pool est actif et tente de le reconnecter si nécessaire."""
        if not self.pool:
            logging.warning("Le pool est fermé. Tentative de reconnexion...")
            await self.connect()
        else:
            try:
                async with self.pool.acquire() as connection:
                    await connection.execute('SELECT 1;')  # Vérification simple
            except Exception as e:
                logging.error(f"Erreur lors de la vérification de la connexion : {e}")
                await self.connect()

    async def execute(self, query, *args):
        try:
            async with self.pool.acquire() as connection:
                return await connection.execute(query, *args)
        except Exception as e:
            logging.error(f"Erreur lors de l'exécution de la requête : {e}")
            return None

    async def fetch(self, query, *args):
        try:
            async with self.pool.acquire() as connection:
                return await connection.fetch(query, *args)
        except Exception as e:
            logging.error(f"Erreur lors de la récupération des données : {e}")
            return []

    async def fetchrow(self, query, *args):
        try:
            async with self.pool.acquire() as connection:
                return await connection.fetchrow(query, *args)
        except Exception as e:
            logging.error(f"Erreur lors de la récupération d'une ligne : {e}")
            return None

    async def fetchval(self, query, *args):
        try:
            async with self.pool.acquire() as connection:
                return await connection.fetchval(query, *args)
        except Exception as e:
            logging.error(f"Erreur lors de la récupération d'une valeur : {e}")
            return None
        
    async def purge_old_logs_and_clean_relations(self, days=30):
        """Supprime les anciens logs et nettoie les tables de relation inutilisées."""
        # Supprimer les logs anciens
        delete_logs_query = f"DELETE FROM message_deletions WHERE timestamp < NOW() - INTERVAL '{days} days';"
        await self.execute(delete_logs_query)

        # Nettoyer les tables relationnelles
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

        logging.info("Logs obsolètes et données relationnelles non utilisées supprimés.")

    async def log_message_deletion(self, deleted_by, channel, guild, deletion_type, target_user, message_count):
        """Enregistre une suppression de messages dans la base de données."""
        if message_count is None or message_count <= 0:
            logging.error("Le nombre de messages supprimés est invalide ou manquant.")
            raise ValueError("message_count ne peut pas être vide ou nul.")

        deleted_by_id = await self.get_or_create_id('user_id', 'username', deleted_by)
        channel_id = await self.get_or_create_id('channel_id', 'channel', channel)
        guild_id = await self.get_or_create_id('serveur_id', 'serveur', guild)
        deletion_type_id = await self.get_or_create_id('deletion_id', 'type', deletion_type)
        target_user_id = await self.get_or_create_id('user_id', 'username', target_user) if target_user else None
        message_count_id = await self.get_or_create_id('nombre_id', 'nombre', message_count)

        query = """
            INSERT INTO message_deletions 
            (deleted_by, channel_id, guild_id, deletion_type, target_user, message_count, timestamp)
            VALUES ($1, $2, $3, $4, $5, $6, NOW())
        """
        await self.execute(query, deleted_by_id, channel_id, guild_id, deletion_type_id, target_user_id, message_count_id)


    async def get_or_create_id(self, table, column, value):
        """Récupère ou insère une valeur dans une table spécifique."""
        if not value:
            raise ValueError(f"La valeur pour {column} ne peut pas être vide.")

        try:
            # Vérification de l'existence
            query_select = f"SELECT id FROM {table} WHERE {column} = $1;"
            result = await self.fetchval(query_select, value)
            if result:
                return result

            # Insertion si non existant
            query_insert = f"INSERT INTO {table} ({column}) VALUES ($1) RETURNING id;"
            return await self.fetchval(query_insert, value)
        except Exception as e:
            logging.error(f"Erreur SQL dans get_or_create_id pour {table}.{column} avec valeur '{value}': {e}")
            raise

    async def get_message_deletions(self, limit=50):
        """Récupère les suppressions avec informations complètes."""
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
        return await database.fetch(query, limit)


# Singleton pour éviter les multiples instances
database = Database()
