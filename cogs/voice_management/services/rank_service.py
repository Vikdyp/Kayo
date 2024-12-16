#cogs\voice_management\services\rank_service.py
from utils.database import database
import logging

logger = logging.getLogger('services.rank_service')

class RankService:
    @staticmethod
    async def get_config(guild_id: int):
        """Récupère les configurations des rôles et canaux pour un serveur spécifique."""
        query_roles = """
        SELECT role_name, role_id 
        FROM public.roles_configurations
        WHERE role_name IN ('fer', 'bronze', 'argent', 'or', 'platine', 'diamant', 'ascendant', 'immortel', 'radiant')
        AND guild_id = $1
        ORDER BY role_name ASC;
        """
        
        query_channels = """
        SELECT action, channel_id
        FROM public.channel_configurations
        WHERE action IN ('fer', 'bronze', 'argent', 'or', 'platine', 'diamant', 'ascendant', 'immortel', 'radiant')
        AND guild_id = $1
        ORDER BY action ASC;
        """

        try:
            roles = await database.fetch(query_roles, guild_id)
            channels = await database.fetch(query_channels, guild_id)

            return {
                "roles": {row['role_name']: row['role_id'] for row in roles},
                "channels": {row['action']: row['channel_id'] for row in channels}
            }
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des configurations pour le serveur {guild_id} : {e}")
            return {"roles": {}, "channels": {}}
