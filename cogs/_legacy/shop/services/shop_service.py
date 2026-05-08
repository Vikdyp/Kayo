import logging
from typing import Optional

from utils.database import database

logger = logging.getLogger(__name__)

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

async def is_bundle_sent(bundle_uuid: str) -> bool:
    """Vérifie si le bundle a déjà été notifié."""
    query = """
        SELECT EXISTS(
            SELECT 1
              FROM valorant_sent_bundles
             WHERE bundle_uuid = $1
        );
    """
    try:
        return await database.fetchval(query, bundle_uuid)
    except Exception as e:
        logger.error(f"Erreur is_bundle_sent pour bundle {bundle_uuid}: {e}")
        return False

async def mark_bundle_sent(bundle_uuid: str) -> None:
    """Enregistre le bundle comme notifié."""
    query = """
        INSERT INTO valorant_sent_bundles (bundle_uuid, notified_at)
        VALUES ($1, NOW())
        ON CONFLICT (bundle_uuid) DO NOTHING;
    """
    try:
        await database.execute(query, bundle_uuid)
    except Exception as e:
        logger.error(f"Erreur mark_bundle_sent pour bundle {bundle_uuid}: {e}")