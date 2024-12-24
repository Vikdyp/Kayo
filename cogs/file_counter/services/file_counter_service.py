# cogs/file_counter/services/file_counter_service.py

from typing import Optional, Dict
import logging
from utils.database import database

logger = logging.getLogger("services.file_counter_service")

class FileCounterService:
    @staticmethod
    async def get_counter(guild_id: int, channel_id: int) -> Optional[Dict]:
        """
        Récupère les informations du compteur pour un serveur et un salon spécifiques.
        """
        query = """
        SELECT message_id, ajouter_count, terminer_count
        FROM file_counters
        WHERE guild_id = $1 AND channel_id = $2;
        """
        try:
            record = await database.fetchrow(query, guild_id, channel_id)
            if record:
                return {
                    "message_id": record["message_id"],
                    "ajouter_count": record["ajouter_count"],
                    "terminer_count": record["terminer_count"]
                }
            return None
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du compteur pour guild_id={guild_id}, channel_id={channel_id}: {e}")
            return None

    @staticmethod
    async def create_counter(guild_id: int, channel_id: int, message_id: int) -> bool:
        """
        Crée une nouvelle entrée de compteur dans la table `file_counters`.
        """
        query = """
        INSERT INTO file_counters (guild_id, channel_id, message_id, ajouter_count, terminer_count)
        VALUES ($1, $2, $3, 0, 0)
        ON CONFLICT (guild_id, channel_id) DO NOTHING;
        """
        try:
            await database.execute(query, guild_id, channel_id, message_id)
            logger.info(f"Compteur créé pour guild_id={guild_id}, channel_id={channel_id}, message_id={message_id}.")
            return True
        except Exception as e:
            logger.error(f"Erreur lors de la création du compteur pour guild_id={guild_id}, channel_id={channel_id}: {e}")
            return False

    @staticmethod
    async def update_counts(guild_id: int, channel_id: int, ajouter: bool = False, terminer: bool = False) -> Optional[Dict]:
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
        WHERE guild_id = $1 AND channel_id = $2
        RETURNING ajouter_count, terminer_count;
        """
        try:
            record = await database.fetchrow(query, guild_id, channel_id)
            if record:
                return {
                    "ajouter_count": record["ajouter_count"],
                    "terminer_count": record["terminer_count"]
                }
            return None
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour des compteurs pour guild_id={guild_id}, channel_id={channel_id}: {e}")
            return None
