#cogs\configuration\services\role_service.py
import logging
from utils.database import database

logger = logging.getLogger('services.role_service')

class RoleService:
    @staticmethod
    async def get_roles_config(guild_id: int) -> dict:
        """
        Récupère la configuration des rôles pour un serveur spécifique.
        """
        query = """
        SELECT role_name, role_id
        FROM roles_configurations
        WHERE guild_id = $1;
        """
        try:
            records = await database.fetch(query, guild_id)
            if not records:
                logger.warning(f"Aucune configuration trouvée pour guild_id={guild_id}.")
                return {}
            config = {record['role_name']: record['role_id'] for record in records}
            logger.info(f"Configuration des rôles récupérée pour guild_id={guild_id}: {config}")
            return config
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des rôles pour guild_id={guild_id}: {e}")
            return {}

    @staticmethod
    async def set_role_for_action(guild_id: int, role_name: str, role_id: int) -> bool:
        """
        Configure un rôle pour une action spécifique dans un serveur.
        """
        query = """
        INSERT INTO roles_configurations (guild_id, role_name, role_id)
        VALUES ($1, $2, $3)
        ON CONFLICT (guild_id, role_name) DO UPDATE
        SET role_id = EXCLUDED.role_id;
        """
        try:
            await database.execute(query, guild_id, role_name, role_id)
            logger.info(f"Rôle ID={role_id} configuré pour '{role_name}' dans guild_id={guild_id}.")
            return True
        except Exception as e:
            logger.error(f"Erreur lors de la configuration du rôle pour '{role_name}' dans guild_id={guild_id}: {e}")
            return False

    @staticmethod
    async def remove_role_for_action(guild_id: int, role_name: str) -> bool:
        """
        Supprime la configuration d'un rôle pour une action spécifique.
        """
        query = """
        DELETE FROM roles_configurations
        WHERE guild_id = $1 AND role_name = $2;
        """
        try:
            await database.execute(query, guild_id, role_name)
            logger.info(f"Configuration pour le rôle '{role_name}' supprimée dans guild_id={guild_id}.")
            return True
        except Exception as e:
            logger.error(f"Erreur lors de la suppression du rôle '{role_name}' dans guild_id={guild_id}: {e}")
            return False
