from typing import Optional, Dict
import logging
from utils.database import database
from utils.base import get_or_create_server_record

logger = logging.getLogger("services.file_counter_service")

class FileCounterService:

    @staticmethod
    async def get_or_create_server_record(discord_guild_id: int, guild_name: str = "Inconnu") -> Optional[int]:
        """Wrapper vers :func:`utils.base.get_or_create_server_record`."""
        return await get_or_create_server_record(discord_guild_id, guild_name)

    @staticmethod
    async def get_counter(server_db_id: int, channel_id: int) -> Optional[Dict]:
        """
        Récupère les informations du compteur pour un server_db_id et un salon spécifiques.
        """
        query = """
        SELECT message_id, ajouter_count, terminer_count
          FROM file_counters
         WHERE guild_id = $1
           AND channel_id = $2;
        """
        try:
            record = await database.fetchrow(query, server_db_id, channel_id)
            if record:
                return {
                    "message_id": record["message_id"],
                    "ajouter_count": record["ajouter_count"],
                    "terminer_count": record["terminer_count"]
                }
            return None
        except Exception as e:
            logger.error(
                f"Erreur lors de la récupération du compteur pour server_db_id={server_db_id}, channel_id={channel_id}: {e}"
            )
            return None

    @staticmethod
    async def create_counter(server_db_id: int, channel_id: int, message_id: int) -> bool:
        """
        Crée une nouvelle entrée de compteur dans la table `file_counters`.
        """
        query = """
        INSERT INTO file_counters (guild_id, channel_id, message_id, ajouter_count, terminer_count)
        VALUES ($1, $2, $3, 0, 0)
        ON CONFLICT (guild_id, channel_id) DO NOTHING;
        """
        try:
            await database.execute(query, server_db_id, channel_id, message_id)
            logger.info(f"Compteur créé pour server_db_id={server_db_id}, channel_id={channel_id}, message_id={message_id}.")
            return True
        except Exception as e:
            logger.error(
                f"Erreur lors de la création du compteur pour server_db_id={server_db_id}, channel_id={channel_id}: {e}"
            )
            return False

    @staticmethod
    async def update_counts(server_db_id: int, channel_id: int, ajouter: bool = False, terminer: bool = False) -> Optional[Dict]:
        """
        Incrémente les compteurs `ajouter_count` et/ou `terminer_count` dans la table `file_counters`.
        """
        if not ajouter and not terminer:
            return None

        set_clause = []
        if ajouter:
            set_clause.append("ajouter_count = ajouter_count + 1")
        if terminer:
            set_clause.append("terminer_count = terminer_count + 1")
        set_clause_str = ", ".join(set_clause)

        query = f"""
        UPDATE file_counters
           SET {set_clause_str}
         WHERE guild_id = $1
           AND channel_id = $2
        RETURNING ajouter_count, terminer_count;
        """
        try:
            record = await database.fetchrow(query, server_db_id, channel_id)
            if record:
                return {
                    "ajouter_count": record["ajouter_count"],
                    "terminer_count": record["terminer_count"]
                }
            return None
        except Exception as e:
            logger.error(
                f"Erreur lors de la mise à jour des compteurs pour server_db_id={server_db_id}, channel_id={channel_id}: {e}"
            )
            return None

    @staticmethod
    async def reset_counter(server_db_id: int, channel_id: int, message_id: int) -> bool:
        """
        Réinitialise un compteur existant (remet ajouter_count et terminer_count à 0)
        et met à jour le message_id.
        """
        query = """
        UPDATE file_counters
           SET ajouter_count = 0,
               terminer_count = 0,
               message_id = $3
         WHERE guild_id = $1
           AND channel_id = $2
        """
        try:
            await database.execute(query, server_db_id, channel_id, message_id)
            logger.info(f"Compteur réinitialisé pour server_db_id={server_db_id}, channel_id={channel_id}, nouveau message_id={message_id}.")
            return True
        except Exception as e:
            logger.error(
                f"Erreur lors de la réinitialisation du compteur pour server_db_id={server_db_id}, channel_id={channel_id}: {e}"
            )
            return False
