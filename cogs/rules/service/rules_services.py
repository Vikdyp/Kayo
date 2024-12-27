# cogs/ranking/services/rules_service.py

import logging
from typing import Optional
from utils.database import database

logger = logging.getLogger("rules_service")

# =========================================================
# 1) Gérer le salon "rules" via channel_configurations
# =========================================================
async def get_rules_channel_id(guild_id: int) -> Optional[int]:
    """
    Récupère l'ID du salon configuré pour l'action 'rules' 
    dans la table channel_configurations.
    """
    query = """
        SELECT channel_id
          FROM channel_configurations
         WHERE guild_id = $1
           AND action = 'rules'
         LIMIT 1
    """
    channel_id = await database.fetchval(query, guild_id)
    if channel_id:
        logger.debug(f"[get_rules_channel_id] Salon 'rules' pour guild_id={guild_id}: {channel_id}")
    else:
        logger.warning(f"[get_rules_channel_id] Aucun salon configuré pour 'rules' dans guild_id={guild_id}")
    return channel_id

# =========================================================
# 2) Gérer les messages persistants (persistent_messages)
# =========================================================
async def store_rules_message(guild_id: int, channel_id: int, message_id: int) -> bool:
    """
    Stocke (ou met à jour) un message persistant de type 'rules_embed' 
    dans la table persistent_messages.
    """
    query = """
        INSERT INTO persistent_messages (guild_id, channel_id, message_id, message_type)
        VALUES ($1, $2, $3, 'rules_embed')
        ON CONFLICT (guild_id, message_type) DO UPDATE
           SET channel_id = EXCLUDED.channel_id,
               message_id = EXCLUDED.message_id,
               created_at = NOW();
    """
    try:
        await database.execute(query, guild_id, channel_id, message_id)
        logger.info(f"[store_rules_message] rules_embed stocké: guild={guild_id}, msg={message_id}")
        return True
    except Exception as e:
        logger.error(f"[store_rules_message] Erreur: {e}")
        return False

async def get_rules_message(guild_id: int) -> Optional[dict]:
    """
    Récupère le message persistant de type 'rules_embed' pour une guilde donnée.
    Renvoie un dict { 'channel_id': ..., 'message_id': ... } ou None si pas trouvé.
    """
    query = """
        SELECT channel_id, message_id
          FROM persistent_messages
         WHERE guild_id = $1
           AND message_type = 'rules_embed'
         LIMIT 1
    """
    record = await database.fetchrow(query, guild_id)
    if record:
        return {"channel_id": record["channel_id"], "message_id": record["message_id"]}
    return None

# =========================================================
# 3) Enregistrer qu'un utilisateur a accepté le règlement
# =========================================================
async def accept_rules_user(discord_id: int) -> bool:
    """
    Insère l'utilisateur dans la table user_id (colonne discord_id)
    s'il n'existe pas déjà, indiquant qu'il a accepté le règlement.
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
