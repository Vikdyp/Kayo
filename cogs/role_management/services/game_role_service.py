# cogs\role_management\services\game_role_service.py
from typing import Optional, Dict
from utils.database import database
import logging

logger = logging.getLogger("general_service")

async def store_persistent_message(guild_id: int, channel_id: int, message_id: int, message_type: str) -> bool:
    """
    Stocke ou met à jour les informations d'un message persistant dans la base de données.
    
    :param guild_id: ID de la guilde Discord.
    :param channel_id: ID du salon Discord.
    :param message_id: ID du message Discord.
    :param message_type: Type du message (e.g., 'role_selection', 'welcome').
    :return: True si réussi, False sinon.
    """
    query = """
        INSERT INTO persistent_messages (guild_id, channel_id, message_id, message_type)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (guild_id, message_type) DO UPDATE
        SET channel_id = EXCLUDED.channel_id,
            message_id = EXCLUDED.message_id,
            created_at = now();
    """
    try:
        await database.execute(query, guild_id, channel_id, message_id, message_type)
        logger.info(f"Message persistant stocké: guild_id={guild_id}, channel_id={channel_id}, message_id={message_id}, type={message_type}")
        return True
    except Exception as e:
        logger.error(f"Erreur lors du stockage du message persistant: {e}")
        return False

async def get_persistent_message(guild_id: int, message_type: str) -> Optional[Dict[str, int]]:
    """
    Récupère les informations d'un message persistant spécifique.
    
    :param guild_id: ID de la guilde Discord.
    :param message_type: Type du message.
    :return: Dictionnaire avec 'channel_id' et 'message_id' ou None si non trouvé.
    """
    query = """
        SELECT channel_id, message_id 
        FROM persistent_messages 
        WHERE guild_id = $1 AND message_type = $2;
    """
    record = await database.fetchrow(query, guild_id, message_type)
    if record:
        logger.debug(f"Message persistant récupéré: guild_id={guild_id}, type={message_type}, channel_id={record['channel_id']}, message_id={record['message_id']}")
        return {'channel_id': record['channel_id'], 'message_id': record['message_id']}
    else:
        logger.warning(f"Aucun message persistant trouvé pour guild_id={guild_id} et type={message_type}.")
        return None

async def delete_persistent_message(guild_id: int, message_type: str) -> bool:
    """
    Supprime les informations d'un message persistant de la base de données.
    
    :param guild_id: ID de la guilde Discord.
    :param message_type: Type du message.
    :return: True si réussi, False sinon.
    """
    query = """
        DELETE FROM persistent_messages 
        WHERE guild_id = $1 AND message_type = $2;
    """
    try:
        await database.execute(query, guild_id, message_type)
        logger.info(f"Message persistant supprimé: guild_id={guild_id}, type={message_type}")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de la suppression du message persistant: {e}")
        return False
    
async def get_role_id(guild_id: int, role_name: str) -> Optional[int]:
    """
    Récupère l'ID du rôle pour un nom d'action spécifique dans une guilde donnée.
    
    :param guild_id: ID de la guilde Discord.
    :param role_name: Nom de l'action (e.g., 'initiator', 'controller', etc.).
    :return: ID du rôle ou None si non trouvé.
    """
    query = """
        SELECT role_id 
        FROM roles_configurations 
        WHERE guild_id = $1 AND role_name = $2;
    """
    role_id = await database.fetchval(query, guild_id, role_name)
    if role_id:
        logger.debug(f"Rôle trouvé: guild_id={guild_id}, role_name={role_name}, role_id={role_id}")
    else:
        logger.warning(f"Aucun rôle trouvé: guild_id={guild_id}, role_name={role_name}")
    return role_id

async def get_all_role_ids(guild_id: int, role_names: list) -> Dict[str, int]:
    """
    Récupère les IDs des rôles pour une liste de noms d'actions dans une guilde donnée.
    
    :param guild_id: ID de la guilde Discord.
    :param role_names: Liste des noms d'actions.
    :return: Dictionnaire avec les noms d'actions comme clés et les IDs des rôles comme valeurs.
    """
    query = """
        SELECT role_name, role_id 
        FROM roles_configurations 
        WHERE guild_id = $1 AND role_name = ANY($2::text[]);
    """
    records = await database.fetch(query, guild_id, role_names)
    roles = {record['role_name']: record['role_id'] for record in records}
    logger.debug(f"Rôles récupérés pour guild_id={guild_id}: {roles}")
    return roles