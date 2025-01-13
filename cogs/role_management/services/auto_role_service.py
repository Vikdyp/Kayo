# cogs\role_management\services\auto_role_service.py

import logging
from typing import Optional
from utils.database import database

logger = logging.getLogger('auto_role_service')

class AutoRoleService:
    @staticmethod
    async def get_server_id(guild_id: int) -> Optional[int]:
        """
        Récupère l'ID interne du serveur à partir de l'ID de la guilde Discord.
        
        :param guild_id: L'ID de la guilde Discord.
        :return: L'ID interne du serveur ou None si non trouvé.
        """
        try:
            query = """
                SELECT id 
                FROM serveur_id 
                WHERE guild_id = $1;
            """
            server_id = await database.fetchval(query, guild_id)
            if server_id:
                logger.info(f"Serveur interne trouvé pour guild_id {guild_id}: server_id={server_id}")
            else:
                logger.warning(f"Serveur interne non trouvé pour guild_id {guild_id}.")
            return server_id
        except Exception as e:
            logger.error(f"Erreur lors de la récupération de server_id pour guild_id {guild_id}: {e}")
            return None

    @staticmethod
    async def get_tester_role_id(guild_id: int) -> Optional[int]:
        """
        Récupère l'ID du rôle 'tester' pour un serveur spécifique depuis la table roles_configurations.
        
        Args:
            guild_id (int): L'ID Discord de la guilde.
        
        Returns:
            Optional[int]: L'ID du rôle 'tester' si trouvé, sinon None.
        """
        try:
            # Récupérer l'ID interne du serveur
            server_id = await AutoRoleService.get_server_id(guild_id)
            if server_id is None:
                logger.warning(f"Serveur interne non trouvé pour guild_id {guild_id}.")
                return None

            query = """
                SELECT role_id
                FROM roles_configurations
                WHERE server_id = $1 AND role_name = 'tester';
            """
            record = await database.fetchrow(query, server_id)
            if record:
                role_id = record['role_id']
                logger.info(f"Rôle 'tester' trouvé pour server_id {server_id}: role_id={role_id}")
                return role_id
            else:
                logger.warning(f"Rôle 'tester' non trouvé pour server_id {server_id}.")
                return None
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du rôle 'tester' pour guild_id {guild_id}: {e}")
            return None
