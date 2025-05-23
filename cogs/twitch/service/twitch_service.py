# cogs\twitch\service\twitch_service.py

import logging
from typing import List, Optional

from utils.database import database

logger = logging.getLogger("twitch.service")


class StreamerService:
    """
    Service pour gérer les streamers partenaires et récupérer le salon de notification Twitch.
    """

    @staticmethod
    async def _get_server_id(guild_id: int) -> Optional[int]:
        """
        Récupère l'id interne du serveur (table serveur_id) à partir du guild_id Discord.
        """
        query = "SELECT id FROM serveur_id WHERE guild_id = $1;"
        try:
            return await database.fetchval(query, guild_id)
        except Exception as e:
            logger.error(f"Erreur fetch server_id pour guild {guild_id}: {e}")
            return None

    @staticmethod
    async def add_streamer(guild_id: int, streamer: str) -> bool:
        server_id = await StreamerService._get_server_id(guild_id)
        if not server_id:
            return False
        query = """
        INSERT INTO streamer_partners (server_id, streamer_name)
        VALUES ($1, $2)
        ON CONFLICT DO NOTHING;
        """
        try:
            await database.execute(query, server_id, streamer.lower())
            return True
        except Exception as e:
            logger.error(f"Erreur add_streamer: {e}")
            return False

    @staticmethod
    async def remove_streamer(guild_id: int, streamer: str) -> bool:
        server_id = await StreamerService._get_server_id(guild_id)
        if not server_id:
            return False
        query = """
        DELETE FROM streamer_partners
         WHERE server_id = $1
           AND streamer_name = $2;
        """
        try:
            result = await database.execute(query, server_id, streamer.lower())
            return result.startswith("DELETE")
        except Exception as e:
            logger.error(f"Erreur remove_streamer: {e}")
            return False

    @staticmethod
    async def list_streamers(guild_id: int) -> List[str]:
        server_id = await StreamerService._get_server_id(guild_id)
        if not server_id:
            return []
        query = "SELECT streamer_name FROM streamer_partners WHERE server_id = $1;"
        try:
            rows = await database.fetch(query, server_id)
            return [r["streamer_name"] for r in rows]
        except Exception as e:
            logger.error(f"Erreur list_streamers: {e}")
            return []

    @staticmethod
    async def get_notify_channel_id(guild_id: int) -> Optional[int]:
        """
        Récupère le channel_id configuré dans channel_configurations
        pour l'action 'twitch' de ce guild.
        """
        query = """
        SELECT cc.channel_id
          FROM channel_configurations cc
          JOIN serveur_id s ON cc.server_id = s.id
         WHERE s.guild_id = $1
           AND cc.action = 'twitch';
        """
        try:
            return await database.fetchval(query, guild_id)
        except Exception as e:
            logger.error(f"Erreur get_notify_channel_id pour guild {guild_id}: {e}")
            return None
