# cogs/role_management/services/language_role_service.py

from utils.database import database
import logging
from typing import Optional, Dict, List

logger = logging.getLogger("RoleService")


class RoleService:
    @staticmethod
    async def get_role_id(server_id: int, role_name: str, guild_name: str = "Inconnu") -> Optional[int]:
        """
        Récupère l'ID du rôle depuis la table `roles_configurations`.
        """
        query = """
        SELECT role_id
        FROM roles_configurations
        WHERE server_id = $1 AND role_name = $2;
        """
        try:
            role_id = await database.fetchval(query, server_id, role_name)
            if role_id:
                logger.debug(f"Rôle '{role_name}' trouvé avec ID {role_id} pour server_id={server_id}.")
            else:
                logger.debug(f"Aucun rôle '{role_name}' trouvé pour server_id={server_id}.")
            return role_id
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du rôle '{role_name}' pour server_id={server_id} : {e}")
            return None

    @staticmethod
    async def store_persistent_message(discord_guild_id: int, channel_id: int, message_id: int, message_type: str, guild_name: str = "Inconnu") -> bool:
        """
        Stocke ou met à jour les informations d'un message persistant dans la base de données.
        """
        try:
            server_db_id = await RoleService.get_or_create_server_record(discord_guild_id, guild_name)
            if not server_db_id:
                logger.error(f"Échec de la récupération ou de la création de server_db_id pour guild_id={discord_guild_id}.")
                return False

            query = """
                INSERT INTO persistent_messages (guild_id, channel_id, message_id, message_type, created_at)
                VALUES ($1, $2, $3, $4, NOW())
                ON CONFLICT (guild_id, message_type) DO UPDATE
                SET channel_id = EXCLUDED.channel_id,
                    message_id = EXCLUDED.message_id,
                    created_at = NOW();
            """
            await database.execute(query, server_db_id, channel_id, message_id, message_type)
            logger.info(
                f"Message persistant stocké: server_db_id={server_db_id}, "
                f"channel_id={channel_id}, message_id={message_id}, type={message_type}"
            )
            return True
        except Exception as e:
            logger.error(f"Erreur lors du stockage du message persistant : {e}")
            return False

    @staticmethod
    async def get_persistent_message(discord_guild_id: int, message_type: str, guild_name: str = "Inconnu") -> Optional[Dict[str, int]]:
        """
        Récupère les informations d'un message persistant spécifique.
        """
        try:
            server_db_id = await RoleService.get_or_create_server_record(discord_guild_id, guild_name)
            if not server_db_id:
                logger.error(f"Échec de la récupération ou de la création de server_db_id pour guild_id={discord_guild_id}.")
                return None

            query = """
                SELECT channel_id, message_id
                FROM persistent_messages
                WHERE guild_id = $1
                  AND message_type = $2;
            """
            record = await database.fetchrow(query, server_db_id, message_type)
            if record:
                logger.debug(
                    f"Message persistant récupéré: server_db_id={server_db_id}, type={message_type}, "
                    f"channel_id={record['channel_id']}, message_id={record['message_id']}"
                )
                return {'channel_id': record['channel_id'], 'message_id': record['message_id']}
            else:
                logger.warning(
                    f"Aucun message persistant trouvé pour server_db_id={server_db_id} et type={message_type}."
                )
                return None
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du message persistant : {e}")
            return None

    @staticmethod
    async def delete_persistent_message(discord_guild_id: int, message_type: str, guild_name: str = "Inconnu") -> bool:
        """
        Supprime les informations d'un message persistant de la base de données.
        """
        try:
            server_db_id = await RoleService.get_or_create_server_record(discord_guild_id, guild_name)
            if not server_db_id:
                logger.error(f"Échec de la récupération ou de la création de server_db_id pour guild_id={discord_guild_id}.")
                return False

            query = """
                DELETE FROM persistent_messages
                WHERE guild_id = $1 AND message_type = $2;
            """
            await database.execute(query, server_db_id, message_type)
            logger.info(f"Message persistant supprimé: server_db_id={server_db_id}, type={message_type}")
            return True
        except Exception as e:
            logger.error(f"Erreur lors de la suppression du message persistant : {e}")
            return False

    @staticmethod
    async def get_or_create_server_record(discord_guild_id: int, guild_name: str = "Inconnu") -> Optional[int]:
        """
        Récupère ou crée l'ID interne (PK) de la table serveur_id pour un guild_id (Discord) donné.
        """
        try:
            select_query = """
                SELECT id
                FROM serveur_id
                WHERE guild_id = $1;
            """
            record = await database.fetchrow(select_query, discord_guild_id)
            if record:
                logger.debug(f"Serveur existant trouvé pour guild_id={discord_guild_id}, id={record['id']}.")
                return record['id']

            insert_query = """
                INSERT INTO serveur_id (guild_id, serveur)
                VALUES ($1, $2)
                RETURNING id;
            """
            new_id = await database.fetchval(insert_query, discord_guild_id, guild_name)
            logger.info(f"[get_or_create_server_record] Serveur créé pour guild_id={discord_guild_id}, id={new_id}")
            return new_id
        except Exception as e:
            logger.error(f"[get_or_create_server_record] Erreur : {e}")
            return None

    @staticmethod
    async def get_all_role_ids(discord_guild_id: int, role_names: List[str], guild_name: str = "Inconnu") -> Dict[str, int]:
        """
        Récupère les IDs des rôles Discord pour une liste de noms de rôles dans une guilde donnée.
        """
        try:
            server_db_id = await RoleService.get_or_create_server_record(discord_guild_id, guild_name)
            if not server_db_id:
                logger.error(f"Échec de la récupération ou de la création de server_db_id pour guild_id={discord_guild_id}.")
                return {}

            query = """
                SELECT role_name, role_id
                FROM roles_configurations
                WHERE server_id = $1
                  AND role_name = ANY($2::text[]);
            """
            records = await database.fetch(query, server_db_id, role_names)
            roles = {record['role_name']: record['role_id'] for record in records}
            logger.debug(f"Rôles récupérés pour server_db_id={server_db_id}: {roles}")
            return roles
        except Exception as e:
            logger.error(f"[get_all_role_ids] Erreur : {e}")
            return {}
