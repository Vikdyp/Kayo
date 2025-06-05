# cogs/configuration/services/server_role_service.py

import logging
from utils.database import database

logger = logging.getLogger('services.server_role_service')

class ServerRoleService:
    @staticmethod
    async def get_or_create_server_record(guild_id: int, guild_name: str) -> int:
        """
        Vérifie si le serveur Discord (guild_id) existe déjà dans la table serveur_id.
        Si non, l'insère. Retourne ensuite l'id (PK) de la table serveur_id.
        """
        try:
            # Tenter de récupérer l'ID du serveur
            select_query = """
            SELECT id
            FROM serveur_id
            WHERE guild_id = $1
            """
            record = await database.fetchrow(select_query, guild_id)
            if record:
                logger.debug(f"[ServerRoleService] Serveur existant trouvé: guild_id={guild_id}, id={record['id']}")
                return record["id"]

            # Si le serveur n'existe pas, l'insérer
            insert_query = """
            INSERT INTO serveur_id (guild_id, serveur)
            VALUES ($1, $2)
            RETURNING id;
            """
            new_id = await database.fetchval(insert_query, guild_id, guild_name)
            logger.info(f"[ServerRoleService] Serveur créé: guild_id={guild_id}, id={new_id}")
            return new_id

        except Exception as e:
            logger.error(f"[ServerRoleService] Erreur lors de la récupération/création du serveur {guild_id}: {e}")
            return None

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

    @staticmethod
    async def get_role_for_action(guild_id: int, guild_name: str, role_name: str):
        """Récupère le role_id configuré pour un rôle spécifique."""
        try:
            server_db_id = await ServerRoleService.get_or_create_server_record(guild_id, guild_name)
            if not server_db_id:
                return None

            query = """
            SELECT role_id
              FROM roles_configurations
             WHERE server_id = $1 AND role_name = $2
             LIMIT 1;
            """
            return await database.fetchval(query, server_db_id, role_name)
        except Exception as e:
            logger.error(f"[ServerRoleService] Erreur get_role_for_action: {e}")
            return None
