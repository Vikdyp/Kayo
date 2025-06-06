#cogs\rules\service\rules_services.py
import logging
from typing import Optional, Dict
from utils.database import database
from services.base import get_or_create_server_record, store_persistent_message, get_persistent_message, delete_persistent_message

logger = logging.getLogger("rules_service")

# 2) Gérer le salon "rules"
# ------------------------------------------------
async def get_rules_channel_id(discord_guild_id: int, guild_name: str = "Inconnu") -> Optional[int]:
    """
    Récupère l'ID du salon configuré pour l'action 'rules' 
    dans la table channel_configurations (FK: server_id).
    """
    try:
        server_db_id = await get_or_create_server_record(discord_guild_id, guild_name)
        if not server_db_id:
            return None

        query = """
            SELECT channel_id
              FROM channel_configurations
             WHERE server_id = $1
               AND action = 'rules'
             LIMIT 1
        """
        channel_id = await database.fetchval(query, server_db_id)
        if channel_id:
            logger.debug(f"[get_rules_channel_id] Salon 'rules' pour server_id={server_db_id}: {channel_id}")
        else:
            logger.warning(f"[get_rules_channel_id] Aucun salon configuré pour 'rules' dans server_id={server_db_id}")
        return channel_id
    except Exception as e:
        logger.error(f"[get_rules_channel_id] Erreur : {e}")
        return None

# ------------------------------------------------
# 3) Messages persistants
# ------------------------------------------------
async def store_rules_message(discord_guild_id: int,
                             guild_name: str,
                             channel_id: int,
                             message_id: int) -> bool:
    """Enregistre le message persistant de type ``rules_embed``."""
    return await store_persistent_message(
        discord_guild_id,
        channel_id,
        message_id,
        "rules_embed",
        guild_name,
    )


# ------------------------------------------------
# 4) Enregistrement des utilisateurs
# ------------------------------------------------
async def accept_rules_user(discord_id: int) -> bool:
    """
    Enregistre qu'un utilisateur a accepté le règlement.
    """
    query = """
        INSERT INTO user_id (discord_id)
        VALUES ($1)
        ON CONFLICT (discord_id) DO NOTHING;
    """
    try:
        await database.execute(query, discord_id)
        logger.info(f"[accept_rules_user] L'utilisateur {discord_id} a accepté le règlement.")
        return True
    except Exception as e:
        logger.error(f"[accept_rules_user] Erreur pour {discord_id}: {e}")
        return False
    
async def has_accepted_rules(discord_id: int) -> bool:
    """
    Vérifie si un utilisateur a déjà accepté le règlement.
    """
    query = """
        SELECT COUNT(*)
        FROM user_id
        WHERE discord_id = $1;
    """
    try:
        logger.debug(f"[has_accepted_rules] Vérification pour discord_id={discord_id}")
        result = await database.fetchval(query, discord_id)
        logger.debug(f"[has_accepted_rules] Résultat COUNT={result} pour discord_id={discord_id}")
        return result > 0
    except Exception as e:
        logger.error(f"[has_accepted_rules] Erreur pour {discord_id}: {e}")
        return False


