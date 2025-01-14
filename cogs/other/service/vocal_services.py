#cogs\other\service\vocal_services.py
import logging
from typing import Optional, Tuple
from utils.database import database  # Assurez-vous que ce module est correctement configuré

logger = logging.getLogger("vocal.services")

async def get_server_id(guild_id: int) -> Optional[int]:
    query = """
        SELECT id 
        FROM serveur_id 
        WHERE guild_id = $1;
    """
    try:
        logger.debug(f"Exécution de la requête pour obtenir le server_id pour guild_id={guild_id}")
        return await database.fetchval(query, guild_id)
    except Exception as e:
        logger.error(f"Erreur lors de la récupération de server_id pour guild_id={guild_id}: {e}")
        return None


async def ensure_server_exists(guild_id: int, server_name: str) -> Optional[int]:
    """
    Vérifie si le serveur (identifié par son guild_id) existe dans la table 'serveur_id'.
    S'il n'existe pas, insère une nouvelle entrée avec le nom réel du serveur et retourne l'ID interne.
    """
    server_id = await get_server_id(guild_id)
    if server_id is None:
        query = """
            INSERT INTO serveur_id (serveur, guild_id)
            VALUES ($1, $2)
            RETURNING id;
        """
        try:
            logger.debug(f"Tentative d'insertion dans 'serveur_id' : serveur={server_name}, guild_id={guild_id}")
            server_id = await database.fetchval(query, server_name, guild_id)
            logger.info(f"Création de l'entrée dans 'serveur_id' pour guild {guild_id} (server_id: {server_id}).")
        except Exception as e:
            logger.error(f"Erreur lors de l'insertion dans serveur_id pour guild {guild_id}: {e}")
            return None
    return server_id

async def get_persistent_message(guild_id: int, message_type: str) -> Optional[Tuple[int, int]]:
    """
    Récupère (channel_id, message_id) pour un message persistant dans 'persistent_messages'
    en utilisant l'ID interne du serveur.
    """
    server_id = await get_server_id(guild_id)
    if not server_id:
        logger.warning(f"Serveur ID non trouvé pour guild {guild_id}.")
        return None
    query = """
        SELECT channel_id, message_id
        FROM persistent_messages
        WHERE guild_id = $1 AND message_type = $2;
    """
    try:
        logger.debug(f"Recherche d'un message persistant pour guild_id={guild_id}, message_type={message_type}")
        row = await database.fetchrow(query, server_id, message_type)
        if row:
            logger.info(f"Message persistant trouvé pour guild_id={guild_id}, message_type={message_type}.")
            return (row["channel_id"], row["message_id"])
        logger.warning(f"Message persistant '{message_type}' non trouvé (guild={guild_id}).")
    except Exception as e:
        logger.error(f"Erreur get_persistent_message: {e}")
    return None

async def save_persistent_message(discord_guild_id: int, message_type: str,
                                  channel_id: int, message_id: int,
                                  requester_id: Optional[int] = None) -> None:
    """
    Sauvegarde (ou met à jour) un message persistant dans la table 'persistent_messages'.
    """
    server_id = await get_server_id(discord_guild_id)
    if not server_id:
        logger.error(f"Impossible de save_persistent_message: server_id introuvable pour {discord_guild_id}.")
        return
    query = """
        INSERT INTO persistent_messages (guild_id, message_type, channel_id, message_id, requester_id)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (guild_id, message_type)
        DO UPDATE SET channel_id = EXCLUDED.channel_id, message_id = EXCLUDED.message_id, requester_id = EXCLUDED.requester_id;
    """
    try:
        logger.debug(f"Préparation de l'insertion/mise à jour dans 'persistent_messages': "
                     f"guild_id={server_id}, message_type={message_type}, "
                     f"channel_id={channel_id}, message_id={message_id}, requester_id={requester_id}")
        await database.execute(query, server_id, message_type, channel_id, message_id, requester_id)
        logger.info(f"Message persistant '{message_type}' sauvegardé pour guild {discord_guild_id}.")
    except Exception as e:
        logger.error(f"Erreur save_persistent_message: {e}")
