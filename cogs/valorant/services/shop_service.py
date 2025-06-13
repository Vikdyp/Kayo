import logging
from typing import Optional

from utils.database import database

logger = logging.getLogger("valorant.shop_service")

ACTION_NAME = "valorant_shop"

async def get_notify_channel_id(guild_id: int) -> Optional[int]:
    """Récupère le salon configuré pour les notifications de boutique Valorant."""
    query = """
        SELECT cc.channel_id
          FROM channel_configurations cc
          JOIN serveur_id s ON cc.server_id = s.id
         WHERE s.guild_id = $1
           AND cc.action = $2;
    """
    try:
        return await database.fetchval(query, guild_id, ACTION_NAME)
    except Exception as e:
        logger.error(f"Erreur get_notify_channel_id pour guild {guild_id}: {e}")
        return None

