# cogs/role_management/services/language_role_service.py

from utils.database import database
import logging
from services.base import get_or_create_server_record, store_persistent_message, get_persistent_message, delete_persistent_message
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
        """Enregistre ou met à jour un message persistant."""
        return await store_persistent_message(
            discord_guild_id,
            channel_id,
            message_id,
            message_type,
            guild_name,
        )

    @staticmethod
    async def get_persistent_message(discord_guild_id: int, message_type: str, guild_name: str = "Inconnu") -> Optional[Dict[str, int]]:
        """Récupère un message persistant pour la guilde donnée."""
        return await get_persistent_message(discord_guild_id, message_type, guild_name)

    @staticmethod
    async def delete_persistent_message(discord_guild_id: int, message_type: str, guild_name: str = "Inconnu") -> bool:
        """Supprime un message persistant."""
        return await delete_persistent_message(discord_guild_id, message_type, guild_name)

    @staticmethod
    async def get_or_create_server_record(discord_guild_id: int, guild_name: str = "Inconnu") -> Optional[int]:
        """Retourne l'identifiant interne du serveur, en le créant si besoin."""
        return await get_or_create_server_record(discord_guild_id, guild_name)

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
