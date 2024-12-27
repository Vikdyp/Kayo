from typing import Optional, Dict, List
from utils.database import database
import logging

logger = logging.getLogger("game_role_service")

# ------------------------------------------------
# NOUVEAU : get_or_create_server_record
# ------------------------------------------------
async def get_or_create_server_record(discord_guild_id: int, guild_name: str = "Inconnu") -> Optional[int]:
    """
    Récupère ou crée l'ID interne (PK) de la table serveur_id pour un guild_id (Discord) donné.
    """
    try:
        select_query = """
            SELECT id
              FROM serveur_id
             WHERE guild_id = $1
        """
        record = await database.fetchrow(select_query, discord_guild_id)
        if record:
            return record['id']

        insert_query = """
            INSERT INTO serveur_id (guild_id, serveur)
            VALUES ($1, $2)
            RETURNING id;
        """
        new_id = await database.fetchval(insert_query, discord_guild_id, guild_name)
        logger.info(f"[get_or_create_server_record] Serveur créé pour guild_id={discord_guild_id}, id={new_id}")
        return new_id
    except Exception as e:
        logger.error(f"[get_or_create_server_record] Erreur : {e}")
        return None


# ------------------------------------------------
# PERSISTENT MESSAGES
# ------------------------------------------------

async def store_persistent_message(discord_guild_id: int,
                                  channel_id: int,
                                  message_id: int,
                                  message_type: str,
                                  guild_name: str = "Inconnu") -> bool:
    """
    Stocke ou met à jour les informations d'un message persistant dans la base de données.

    :param discord_guild_id: ID Discord brut de la guilde.
    :param channel_id: ID du salon Discord.
    :param message_id: ID du message Discord.
    :param message_type: Type du message (e.g., 'role_selection', 'welcome').
    :param guild_name: Nom du serveur, par défaut "Inconnu".
    :return: True si réussi, False sinon.
    """
    try:
        server_db_id = await get_or_create_server_record(discord_guild_id, guild_name)
        if not server_db_id:
            return False

        query = """
            INSERT INTO persistent_messages (guild_id, channel_id, message_id, message_type)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id, message_type) DO UPDATE
            SET channel_id = EXCLUDED.channel_id,
                message_id = EXCLUDED.message_id,
                created_at = now();
        """
        await database.execute(query, server_db_id, channel_id, message_id, message_type)
        logger.info(
            f"Message persistant stocké: server_db_id={server_db_id}, "
            f"channel_id={channel_id}, message_id={message_id}, type={message_type}"
        )
        return True
    except Exception as e:
        logger.error(f"Erreur lors du stockage du message persistant: {e}")
        return False

async def get_persistent_message(discord_guild_id: int,
                                message_type: str,
                                guild_name: str = "Inconnu") -> Optional[Dict[str, int]]:
    """
    Récupère les informations d'un message persistant spécifique.

    :param discord_guild_id: ID Discord brut de la guilde.
    :param message_type: Type du message.
    :param guild_name: Nom du serveur, par défaut "Inconnu".
    :return: Dictionnaire avec 'channel_id' et 'message_id' ou None si non trouvé.
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
                f"Message persistant récupéré: server_db_id={server_db_id}, type={message_type}, "
                f"channel_id={record['channel_id']}, message_id={record['message_id']}"
            )
            return {'channel_id': record['channel_id'], 'message_id': record['message_id']}
        else:
            logger.warning(
                f"Aucun message persistant trouvé pour server_db_id={server_db_id} et type={message_type}."
            )
            return None
    except Exception as e:
        logger.error(f"Erreur lors de la récupération du message persistant: {e}")
        return None

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
        logger.info(f"Message persistant supprimé: server_db_id={server_db_id}, type={message_type}")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de la suppression du message persistant: {e}")
        return False


# ------------------------------------------------
# RÔLES
# ------------------------------------------------

async def get_role_id(discord_guild_id: int,
                      role_name: str,
                      guild_name: str = "Inconnu") -> Optional[int]:
    """
    Récupère l'ID du rôle Discord pour un nom d'action spécifique (ex: 'initiator'),
    en utilisant la table roles_configurations et la FK server_id.
    
    :param discord_guild_id: ID Discord brut de la guilde.
    :param role_name: Nom du rôle (ex: 'initiator').
    :param guild_name: Nom de la guilde, par défaut "Inconnu".
    :return: ID du rôle Discord ou None si non trouvé.
    """
    try:
        server_db_id = await get_or_create_server_record(discord_guild_id, guild_name)
        if not server_db_id:
            return None

        query = """
            SELECT role_id 
              FROM roles_configurations 
             WHERE server_id = $1
               AND role_name = $2
        """
        role_id = await database.fetchval(query, server_db_id, role_name)
        if role_id:
            logger.debug(f"Rôle trouvé: server_db_id={server_db_id}, role_name={role_name}, role_id={role_id}")
            return role_id
        else:
            logger.warning(f"Aucun rôle trouvé pour server_db_id={server_db_id}, role_name={role_name}")
            return None
    except Exception as e:
        logger.error(f"[get_role_id] Erreur: {e}")
        return None

async def get_all_role_ids(discord_guild_id: int,
                           role_names: List[str],
                           guild_name: str = "Inconnu") -> Dict[str, int]:
    """
    Récupère les IDs des rôles Discord pour une liste de noms d'actions dans une guilde donnée,
    en passant par la table roles_configurations (FK = server_id).

    :param discord_guild_id: ID Discord brut de la guilde.
    :param role_names: Liste des noms d'actions (ex: ['initiator','duelist',...]).
    :param guild_name: Nom de la guilde, par défaut "Inconnu".
    :return: Dictionnaire {role_name -> role_id}, vide si rien n'est trouvé.
    """
    try:
        server_db_id = await get_or_create_server_record(discord_guild_id, guild_name)
        if not server_db_id:
            return {}

        query = """
            SELECT role_name, role_id 
              FROM roles_configurations 
             WHERE server_id = $1
               AND role_name = ANY($2::text[])
        """
        records = await database.fetch(query, server_db_id, role_names)
        roles = {record['role_name']: record['role_id'] for record in records}
        logger.debug(f"Rôles récupérés pour server_db_id={server_db_id}: {roles}")
        return roles
    except Exception as e:
        logger.error(f"[get_all_role_ids] Erreur: {e}")
        return {}
