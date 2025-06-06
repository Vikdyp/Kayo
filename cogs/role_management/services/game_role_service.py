from typing import Optional, Dict, List
from utils.database import database
import logging
from utils.base import (
    get_or_create_server_record,
    store_persistent_message,
    get_persistent_message,
    delete_persistent_message,
)

logger = logging.getLogger("game_role_service")



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
