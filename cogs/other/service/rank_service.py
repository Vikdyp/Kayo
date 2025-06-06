# cogs/voice_management/services/rank_service.py
from typing import Optional
from utils.database import database
from utils.base import get_or_create_server_record
import logging

logger = logging.getLogger('services.rank_service')

class RankService:
    
    async def get_or_create_server_record(self, guild_id: int, guild_name: str) -> Optional[int]:
        """Wrapper vers :func:`utils.base.get_or_create_server_record`."""
        return await get_or_create_server_record(guild_id, guild_name)

    async def get_config(self, guild_id: int, guild_name: str):
        """
        Récupère les configurations des rôles et canaux pour un serveur spécifique en utilisant server_id.
        """
        # Obtenir l'ID interne du serveur
        server_id = await self.get_or_create_server_record(guild_id, guild_name)
        if server_id is None:
            logger.error(f"[get_config] Impossible d'obtenir ou de créer l'enregistrement du serveur pour guild_id={guild_id}")
            return {"roles": {}, "channels": {}}

        query_roles = """
        SELECT role_name, role_id 
        FROM public.roles_configurations
        WHERE role_name IN ('fer', 'bronze', 'argent', 'or', 'platine', 'diamant', 'ascendant', 'immortel', 'radiant')
        AND server_id = $1
        ORDER BY role_name ASC;
        """
        
        query_channels = """
        SELECT action, channel_id
        FROM public.channel_configurations
        WHERE action IN ('fer', 'bronze', 'argent', 'or', 'platine', 'diamant', 'ascendant', 'immortel', 'radiant')
        AND server_id = $1
        ORDER BY action ASC;
        """

        try:
            roles = await database.fetch(query_roles, server_id)
            channels = await database.fetch(query_channels, server_id)

            return {
                "roles": {row['role_name']: row['role_id'] for row in roles},
                "channels": {row['action']: row['channel_id'] for row in channels}
            }
        except Exception as e:
            logger.error(f"[get_config] Erreur lors de la récupération des configurations pour server_id={server_id} : {e}")
            return {"roles": {}, "channels": {}}
