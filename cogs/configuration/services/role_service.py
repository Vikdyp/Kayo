# cogs/configuration/services/server_role_service.py

import logging
from utils.database import database
from utils.base import get_or_create_server_record

logger = logging.getLogger('services.server_role_service')

class ServerRoleService:
    @staticmethod
    async def get_or_create_server_record(guild_id: int, guild_name: str) -> int:
        """Wrapper vers :func:`utils.base.get_or_create_server_record`."""
        return await get_or_create_server_record(guild_id, guild_name)

    @staticmethod
    async def get_roles_config(guild_id: int, guild_name: str) -> dict:
        """
        Récupère la configuration des rôles pour un serveur.
        Utilise l'ID en base (server_id) pour effectuer la requête.
        """
        try:
            # Récupérer l'ID interne du serveur
            server_db_id = await ServerRoleService.get_or_create_server_record(guild_id, guild_name)
            if not server_db_id:
                return {}

            query = """
            SELECT role_name, role_id
            FROM roles_configurations
            WHERE server_id = $1;
            """
            records = await database.fetch(query, server_db_id)
            if not records:
                logger.warning(f"[ServerRoleService] Aucune configuration de rôle trouvée pour server_id={server_db_id}.")
                return {}

            config = {record['role_name']: record['role_id'] for record in records}
            logger.info(f"[ServerRoleService] Configuration des rôles récupérée pour server_id={server_db_id}: {config}")
            return config

        except Exception as e:
            logger.error(f"[ServerRoleService] Erreur lors de la récupération des rôles pour guild_id={guild_id}: {e}")
            return {}

    @staticmethod
    async def set_role_for_action(guild_id: int, guild_name: str, role_name: str, role_id: int) -> bool:
        """
        Configure un rôle pour une action spécifique, en utilisant server_id comme clé étrangère.
        """
        try:
            server_db_id = await ServerRoleService.get_or_create_server_record(guild_id, guild_name)
            if not server_db_id:
                return False

            query = """
            INSERT INTO roles_configurations (server_id, role_name, role_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (server_id, role_name) DO UPDATE
            SET role_id = EXCLUDED.role_id;
            """
            await database.execute(query, server_db_id, role_name, role_id)
            logger.info(f"[ServerRoleService] Rôle ID={role_id} configuré pour '{role_name}' (server_id={server_db_id}).")
            return True

        except Exception as e:
            logger.error(f"[ServerRoleService] Erreur lors de la configuration du rôle '{role_name}' (guild_id={guild_id}): {e}")
            return False

    @staticmethod
    async def remove_role_for_action(guild_id: int, guild_name: str, role_name: str) -> bool:
        """
        Supprime la configuration d'un rôle pour une action spécifique, via server_id.
        """
        try:
            server_db_id = await ServerRoleService.get_or_create_server_record(guild_id, guild_name)
            if not server_db_id:
                return False

            query = """
            DELETE FROM roles_configurations
            WHERE server_id = $1 AND role_name = $2;
            """
            await database.execute(query, server_db_id, role_name)
            logger.info(f"[ServerRoleService] Rôle '{role_name}' supprimé (server_id={server_db_id}).")
            return True

        except Exception as e:
            logger.error(f"[ServerRoleService] Erreur lors de la suppression du rôle '{role_name}' (guild_id={guild_id}): {e}")
            return False
