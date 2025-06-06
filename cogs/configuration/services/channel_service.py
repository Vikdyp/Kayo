# cogs/configuration/services/channel_service.py

import logging
from utils.database import database
from utils.base import get_or_create_server_record

logger = logging.getLogger('services.server_channel_service')

class ServerChannelService:
    @staticmethod
    async def get_or_create_server_record(guild_id: int, guild_name: str) -> int:
        """Wrapper vers :func:`utils.base.get_or_create_server_record`."""
        return await get_or_create_server_record(guild_id, guild_name)

    @staticmethod
    async def get_channels_config(guild_id: int, guild_name: str) -> dict:
        """
        Récupère la config de tous les salons pour un serveur donné (via l'ID interne).
        """
        try:
            server_db_id = await ServerChannelService.get_or_create_server_record(guild_id, guild_name)
            if not server_db_id:
                return {}

            query = """
            SELECT action, channel_id
            FROM channel_configurations
            WHERE server_id = $1;
            """
            records = await database.fetch(query, server_db_id)
            config = {record['action']: record['channel_id'] for record in records}
            logger.info(f"[ServerChannelService] Salons récupérés pour server_id={server_db_id}: {config}")
            return config

        except Exception as e:
            logger.error(f"[ServerChannelService] Erreur get_channels_config: {e}")
            return {}

    @staticmethod
    async def set_channel_for_action(guild_id: int, guild_name: str, action: str, channel_id: int) -> bool:
        """
        Configure un salon pour une action, en stockant server_id (FK) au lieu du guild_id.
        """
        try:
            server_db_id = await ServerChannelService.get_or_create_server_record(guild_id, guild_name)
            if not server_db_id:
                return False

            query = """
            INSERT INTO channel_configurations (server_id, action, channel_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (server_id, action) DO UPDATE
            SET channel_id = EXCLUDED.channel_id;
            """
            await database.execute(query, server_db_id, action, channel_id)
            logger.info(f"[ServerChannelService] Salon {channel_id} configuré pour '{action}' (server_id={server_db_id}).")
            return True

        except Exception as e:
            logger.error(f"[ServerChannelService] Erreur set_channel_for_action: {e}")
            return False

    @staticmethod
    async def remove_channel_for_action(guild_id: int, guild_name: str, action: str) -> bool:
        """
        Supprime la config d'un salon pour une action, via server_id.
        """
        try:
            server_db_id = await ServerChannelService.get_or_create_server_record(guild_id, guild_name)
            if not server_db_id:
                return False

            query = """
            DELETE FROM channel_configurations
            WHERE server_id = $1 AND action = $2;
            """
            await database.execute(query, server_db_id, action)
            logger.info(f"[ServerChannelService] Config salon '{action}' supprimée (server_id={server_db_id}).")
            return True

        except Exception as e:
            logger.error(f"[ServerChannelService] Erreur remove_channel_for_action: {e}")
            return False
