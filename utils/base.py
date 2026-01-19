import logging
from typing import Optional, Dict

from utils.database import database

logger = logging.getLogger(__name__)

async def get_or_create_server_record(guild_id: int, guild_name: str) -> Optional[int]:
    """Return the internal server ID for a Discord guild, creating the entry if needed."""
    try:
        select_query = """
            SELECT id
              FROM serveur_id
             WHERE guild_id = $1
        """
        record = await database.fetchrow(select_query, guild_id)
        if record:
            return record["id"]

        insert_query = """
            INSERT INTO serveur_id (guild_id, serveur)
            VALUES ($1, $2)
            RETURNING id;
        """
        new_id = await database.fetchval(insert_query, guild_id, guild_name)
        logger.info(
            f"[get_or_create_server_record] Serveur créé pour guild_id={guild_id}, id={new_id}"
        )
        return new_id
    except Exception as e:
        logger.error(f"[get_or_create_server_record] Erreur : {e}")
        return None


async def store_persistent_message(
    discord_guild_id: int,
    channel_id: int,
    message_id: int,
    message_type: str,
    guild_name: str = "Inconnu",
) -> bool:
    """Insert or update a persistent message for the given guild."""
    try:
        server_db_id = await get_or_create_server_record(discord_guild_id, guild_name)
        if not server_db_id:
            return False

        query = """
            INSERT INTO persistent_messages (server_id, channel_id, message_id, message_type)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (server_id, message_type) DO UPDATE
            SET channel_id = EXCLUDED.channel_id,
                message_id = EXCLUDED.message_id,
                created_at = now();
        """
        await database.execute(query, server_db_id, channel_id, message_id, message_type)
        logger.info(
            f"Message persistant stocké: server_db_id={server_db_id}, channel_id={channel_id}, message_id={message_id}, type={message_type}"
        )
        return True
    except Exception as e:
        logger.error(f"Erreur lors du stockage du message persistant: {e}")
        return False


async def get_persistent_message(
    discord_guild_id: int, message_type: str, guild_name: str = "Inconnu"
) -> Optional[Dict[str, int]]:
    """Retrieve the persistent message information for the given guild and type."""
    try:
        server_db_id = await get_or_create_server_record(discord_guild_id, guild_name)
        if not server_db_id:
            return None

        query = """
            SELECT channel_id, message_id
              FROM persistent_messages
             WHERE server_id = $1
               AND message_type = $2
        """
        record = await database.fetchrow(query, server_db_id, message_type)
        if record:
            logger.debug(
                f"Message persistant récupéré: server_db_id={server_db_id}, type={message_type}, channel_id={record['channel_id']}, message_id={record['message_id']}"
            )
            return {"channel_id": record["channel_id"], "message_id": record["message_id"]}
        else:
            logger.warning(
                f"Aucun message persistant trouvé pour server_db_id={server_db_id} et type={message_type}."
            )
            return None
    except Exception as e:
        logger.error(f"Erreur lors de la récupération du message persistant: {e}")
        return None


async def delete_persistent_message(
    discord_guild_id: int, message_type: str, guild_name: str = "Inconnu"
) -> bool:
    """Delete a persistent message entry for the given guild and type."""
    try:
        server_db_id = await get_or_create_server_record(discord_guild_id, guild_name)
        if not server_db_id:
            return False

        query = """
            DELETE FROM persistent_messages
             WHERE server_id = $1
               AND message_type = $2;
        """
        await database.execute(query, server_db_id, message_type)
        logger.info(f"Message persistant supprimé: server_db_id={server_db_id}, type={message_type}")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de la suppression du message persistant: {e}")
        return False
