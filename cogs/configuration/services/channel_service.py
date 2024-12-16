#cogs\configuration\services\channel_service.py

from utils.database import database
import logging

logger = logging.getLogger('services.channel_service')


class ChannelService:
    @staticmethod
    async def get_channels_config(guild_id: int) -> dict:
        """
        Récupère la configuration des salons pour un serveur spécifique.
        """
        query = """
        SELECT action, channel_id
        FROM channel_configurations
        WHERE guild_id = $1;
        """
        try:
            records = await database.fetch(query, guild_id)
            config = {record['action']: record['channel_id'] for record in records}
            logger.info(f"Configuration des salons récupérée pour guild_id={guild_id}: {config}")
            return config
        except Exception as e:
            logger.error(f"Erreur lors de la récupération de la configuration des salons pour guild_id={guild_id}: {e}")
            return {}

    @staticmethod
    async def set_channel_for_action(guild_id: int, action: str, channel_id: int) -> bool:
        """
        Configure un salon pour une action spécifique dans un serveur.
        """
        query = """
        INSERT INTO channel_configurations (guild_id, action, channel_id)
        VALUES ($1, $2, $3)
        ON CONFLICT (guild_id, action) DO UPDATE
        SET channel_id = EXCLUDED.channel_id;
        """
        try:
            await database.execute(query, guild_id, action, channel_id)
            logger.info(f"Salon ID={channel_id} configuré pour l'action '{action}' dans guild_id={guild_id}.")
            return True
        except Exception as e:
            logger.error(f"Erreur lors de la configuration du salon pour l'action '{action}' dans guild_id={guild_id}: {e}")
            return False

    @staticmethod
    async def remove_channel_for_action(guild_id: int, action: str) -> bool:
        """
        Supprime la configuration d'un salon pour une action spécifique dans un serveur.
        """
        query = """
        DELETE FROM channel_configurations
        WHERE guild_id = $1 AND action = $2;
        """
        try:
            await database.execute(query, guild_id, action)
            logger.info(f"Configuration du salon pour l'action '{action}' supprimée dans guild_id={guild_id}.")
            return True
        except Exception as e:
            logger.error(f"Erreur lors de la suppression de la configuration du salon pour l'action '{action}' dans guild_id={guild_id}: {e}")
            return False
