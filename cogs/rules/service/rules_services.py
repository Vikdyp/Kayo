import logging
from typing import Optional, Dict
from utils.database import database

logger = logging.getLogger("rules_service")

# ------------------------------------------------
# NOUVEAU : get_or_create_server_record
# ------------------------------------------------
async def get_or_create_server_record(discord_guild_id: int, guild_name: str = "Inconnu") -> Optional[int]:
    """
    Récupère ou crée l'ID interne (PK) dans la table serveur_id 
    pour un guild_id (Discord) donné.
    """
    try:
        select_query = """
            SELECT id
              FROM serveur_id
             WHERE guild_id = $1
        """
        record = await database.fetchrow(select_query, discord_guild_id)
        if record:
            return record["id"]

        insert_query = """
            INSERT INTO serveur_id (guild_id, serveur)
            VALUES ($1, $2)
            RETURNING id;
        """
        new_id = await database.fetchval(insert_query, discord_guild_id, guild_name)
        logger.info(f"[get_or_create_server_record] Serveur créé: guild_id={discord_guild_id}, id={new_id}")
        return new_id
    except Exception as e:
        logger.error(f"[get_or_create_server_record] Erreur : {e}")
        return None

# =========================================================
# 1) Gérer le salon "rules" via channel_configurations
# =========================================================
async def get_rules_channel_id(discord_guild_id: int, guild_name: str = "Inconnu") -> Optional[int]:
    """
    Récupère l'ID du salon configuré pour l'action 'rules' 
    dans la table channel_configurations (FK: server_id).
    """
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
    try:
        channel_id = await database.fetchval(query, server_db_id)
        if channel_id:
            logger.debug(f"[get_rules_channel_id] Salon 'rules' pour server_id={server_db_id}: {channel_id}")
        else:
            logger.warning(f"[get_rules_channel_id] Aucun salon configuré pour 'rules' dans server_id={server_db_id}")
        return channel_id
    except Exception as e:
        logger.error(f"[get_rules_channel_id] Erreur : {e}")
        return None

# =========================================================
# 2) Gérer les messages persistants (persistent_messages)
# =========================================================
async def store_rules_message(discord_guild_id: int,
                             guild_name: str,
                             channel_id: int,
                             message_id: int) -> bool:
    """
    Stocke (ou met à jour) un message persistant de type 'rules_embed' 
    dans la table persistent_messages.
    
    La colonne persistent_messages.guild_id est un FK vers serveur_id.id
    """
    try:
        server_db_id = await get_or_create_server_record(discord_guild_id, guild_name)
        if not server_db_id:
            return False

        query = """
            INSERT INTO persistent_messages (guild_id, channel_id, message_id, message_type)
            VALUES ($1, $2, $3, 'rules_embed')
            ON CONFLICT (guild_id, message_type) DO UPDATE
               SET channel_id = EXCLUDED.channel_id,
                   message_id = EXCLUDED.message_id,
                   created_at = NOW();
        """
        await database.execute(query, server_db_id, channel_id, message_id)
        logger.info(f"[store_rules_message] rules_embed stocké: server_id={server_db_id}, msg={message_id}")
        return True
    except Exception as e:
        logger.error(f"[store_rules_message] Erreur: {e}")
        return False

async def get_rules_message(discord_guild_id: int,
                           guild_name: str = "Inconnu") -> Optional[Dict[str, int]]:
    """
    Récupère le message persistant de type 'rules_embed'.
    Retourne { 'channel_id': ..., 'message_id': ... } ou None.
    """
    try:
        server_db_id = await get_or_create_server_record(discord_guild_id, guild_name)
        if not server_db_id:
            return None

        query = """
            SELECT channel_id, message_id
              FROM persistent_messages
             WHERE guild_id = $1
               AND message_type = 'rules_embed'
             LIMIT 1
        """
        record = await database.fetchrow(query, server_db_id)
        if record:
            return {"channel_id": record["channel_id"], "message_id": record["message_id"]}
        return None
    except Exception as e:
        logger.error(f"[get_rules_message] Erreur : {e}")
        return None

# =========================================================
# 3) Enregistrer qu'un utilisateur a accepté le règlement
# =========================================================
async def accept_rules_user(discord_id: int) -> bool:
    """
    Insère l'utilisateur dans la table user_id (colonne discord_id)
    s'il n'existe pas déjà, indiquant qu'il a accepté le règlement.
    
    (Cette table n'a pas besoin de server_id, donc on insère juste le discord_id).
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
