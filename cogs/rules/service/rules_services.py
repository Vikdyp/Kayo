#cogs\rules\service\rules_services.py
import logging
from typing import Optional, Dict
from utils.database import database

logger = logging.getLogger("rules_service")

# ------------------------------------------------
# 1) Obtenir ou créer un enregistrement de serveur
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

# ------------------------------------------------
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
    """
    Stocke (ou met à jour) un message persistant de type 'rules_embed' 
    dans la table persistent_messages.
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

async def get_persistent_message(discord_guild_id: int,
                                message_type: str,
                                guild_name: str = "Inconnu") -> Optional[Dict[str, int]]:
    """
    Récupère les informations d'un message persistant spécifique.
    """
    try:
        server_db_id = await get_or_create_server_record(discord_guild_id, guild_name)
        if not server_db_id:
            return None

        query = """
            SELECT channel_id, message_id 
              FROM persistent_messages 
             WHERE guild_id = $1
               AND message_type = $2
        """
        record = await database.fetchrow(query, server_db_id, message_type)
        if record:
            logger.debug(
                f"[get_persistent_message] Message récupéré: server_db_id={server_db_id}, "
                f"type={message_type}, channel_id={record['channel_id']}, message_id={record['message_id']}"
            )
            return {'channel_id': record['channel_id'], 'message_id': record['message_id']}
        else:
            logger.warning(
                f"[get_persistent_message] Aucun message trouvé pour server_db_id={server_db_id}, type={message_type}."
            )
            return None
    except Exception as e:
        logger.error(f"[get_persistent_message] Erreur : {e}")
        return None

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


async def delete_persistent_message(discord_guild_id: int,
                                   message_type: str,
                                   guild_name: str = "Inconnu") -> bool:
    """
    Supprime les informations d'un message persistant de la base de données.

    :param discord_guild_id: ID Discord brut de la guilde.
    :param message_type: Type du message.
    :param guild_name: Nom du serveur, par défaut "Inconnu".
    :return: True si réussi, False sinon.
    """
    try:
        server_db_id = await get_or_create_server_record(discord_guild_id, guild_name)
        if not server_db_id:
            return False

        query = """
            DELETE FROM persistent_messages 
             WHERE guild_id = $1
               AND message_type = $2;
        """
        await database.execute(query, server_db_id, message_type)
        logger.info(f"Message persistant supprimé: server_id={server_db_id}, type={message_type}")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de la suppression du message persistant: {e}")
        return False 
