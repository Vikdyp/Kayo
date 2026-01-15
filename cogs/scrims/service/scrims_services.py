from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import logging
import time
from zoneinfo import ZoneInfo

from utils.database import database  # Module d'accès à la BDD

logger = logging.getLogger("scrims.services")

class SimpleCache:
    def __init__(self, ttl=300):
        self.ttl = ttl
        self.cache = {}

    def get(self, key):
        if key in self.cache:
            value, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl:
                return value
            del self.cache[key]
        return None

    def set(self, key, value):
        self.cache[key] = (value, time.time())

cache = SimpleCache(ttl=600)

class ScrimService:
    """Gestion des scrims et de la persistance via la base de données."""

    async def get_internal_server_id(self, discord_guild_id: int) -> Optional[int]:
        cache_key = f"guild_id:{discord_guild_id}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        query = "SELECT id FROM serveur_id WHERE guild_id = $1;"
        try:
            internal_id = await database.fetchval(query, discord_guild_id)
            cache.set(cache_key, internal_id)
            logger.debug("Récupération de l'ID interne du serveur: discord_guild_id=%s => internal_id=%s", discord_guild_id, internal_id)
            return internal_id
        except Exception:
            logger.exception("Erreur lors de la récupération de l'ID interne du serveur:")
            return None

    async def create_scrim(
        self,
        scrim_datetime: datetime,
        map_name: str,
        rang: str,
        autre: Optional[str],
        initial_participants: List[int],
        message_id: int,
        channel_id: int,
        guild_id: int
    ) -> Optional[int]:
        # ATTENTION : il faut que la table scrims possède les colonnes team1 et team2
        query = """
            INSERT INTO scrims (datetime, map, rang, autre, team1, team2, message_id, channel_id, guild_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING id;
        """
        team1 = initial_participants if initial_participants else []
        team2 = []
        try:
            scrim_id = await database.fetchval(
                query,
                scrim_datetime, map_name, rang, autre, team1, team2, message_id, channel_id, guild_id
            )
            logger.info("Scrim créé avec id %s", scrim_id)
            return scrim_id
        except Exception:
            logger.exception("Erreur lors de la création du scrim:")
            return None

    async def update_scrim_message(self, scrim_id: int, message_id: int) -> None:
        query = "UPDATE scrims SET message_id = $1 WHERE id = $2;"
        await database.execute(query, message_id, scrim_id)

    async def get_internal_user_id(self, discord_id: int) -> Optional[int]:
        query = "SELECT id FROM user_id WHERE discord_id = $1;"
        return await database.fetchval(query, discord_id)

    async def get_scrim_info(self, scrim_id: int) -> Optional[Dict[str, Any]]:
        query = """
            SELECT datetime, map, rang, autre, team1, team2, message_id, channel_id, guild_id 
            FROM scrims WHERE id = $1;
        """
        record = await database.fetchrow(query, scrim_id)
        return dict(record) if record else None

    async def update_scrim_embed_info(self, scrim_id: int) -> Optional[Dict[str, Any]]:
        info = await self.get_scrim_info(scrim_id)
        if not info:
            return None
        team1 = info.get("team1") or []
        team2 = info.get("team2") or []
        info["nb_participants"] = len(team1) + len(team2)
        info["team1"] = team1
        info["team2"] = team2
        return info

    async def delete_scrim(self, scrim_id: int) -> bool:
        query = "DELETE FROM scrims WHERE id = $1;"
        try:
            await database.execute(query, scrim_id)
            logger.info("Scrim %s supprimé", scrim_id)
            return True
        except Exception as e:
            logger.error("Erreur lors de la suppression du scrim %s: %s", scrim_id, e)
            return False

    async def increment_victory(self, internal_user_id: int, server_id: int) -> None:
        update_query = "UPDATE scrim_wins SET wins = wins + 1 WHERE internal_user_id = $1 AND server_id = $2;"
        result = await database.execute(update_query, internal_user_id, server_id)
        if result is None:
            insert_query = "INSERT INTO scrim_wins (internal_user_id, wins, server_id) VALUES ($1, 1, $2);"
            await database.execute(insert_query, internal_user_id, server_id)

    async def get_top50_scrim_players(self, server_id: int) -> List[Dict[str, Any]]:
        query = "SELECT internal_user_id, wins FROM scrim_wins WHERE server_id = $1 ORDER BY wins DESC LIMIT 50;"
        records = await database.fetch(query, server_id)
        return [dict(record) for record in records] if records else []

    async def persist_message(
        self,
        channel_id: int,
        message_id: int,
        message_type: str,
        guild_id: int
    ) -> None:
        query = """
        INSERT INTO persistent_messages (channel_id, message_id, message_type, guild_id, requester_id)
        VALUES ($1, $2, $3, $4, NULL)
        ON CONFLICT (guild_id, message_type)
        DO UPDATE SET channel_id = $1, message_id = $2, requester_id = NULL, created_at = NOW();
        """
        try:
            await database.execute(query, channel_id, message_id, message_type, guild_id)
        except Exception as e:
            logger.error("Erreur lors de la persistance du message : %s", e)

    async def get_persistent_messages(self, message_type: str, guild_id: int) -> List[Dict[str, Any]]:
        query = """
        SELECT channel_id, message_id, message_type, guild_id, created_at
        FROM persistent_messages
        WHERE guild_id = $1 AND message_type = $2;
        """
        records = await database.fetch(query, guild_id, message_type)
        return [dict(record) for record in records] if records else []

    async def get_discord_id(self, internal_id: int) -> Optional[int]:
        query = "SELECT discord_id FROM user_id WHERE id = $1;"
        try:
            discord_id = await database.fetchval(query, internal_id)
            logger.debug("Récupération du discord_id: internal_id=%s => discord_id=%s", internal_id, discord_id)
            return discord_id
        except Exception:
            logger.exception("Erreur lors de la récupération du discord_id pour internal_id=%s:", internal_id)
            return None

    async def get_discord_guild_id(self, internal_id: int) -> Optional[int]:
        query = "SELECT guild_id FROM serveur_id WHERE id = $1;"
        try:
            discord_guild_id = await database.fetchval(query, internal_id)
            return discord_guild_id
        except Exception:
            logger.exception("Erreur lors de la récupération du guild_id pour l'ID interne %s:", internal_id)
            return None

    async def get_active_scrims(self) -> List[Dict[str, Any]]:
        query = "SELECT id, message_id, channel_id FROM scrims WHERE message_id <> 0;"
        try:
            records = await database.fetch(query)
            return [dict(record) for record in records] if records else []
        except Exception as e:
            logger.exception("Erreur lors de la récupération des scrims actifs: %s", e)
            return []

    async def get_active_scrims_full_info(self) -> List[Dict[str, Any]]:
        query = "SELECT * FROM scrims WHERE message_id <> 0;"
        try:
            records = await database.fetch(query)
            return [dict(record) for record in records] if records else []
        except Exception as e:
            logger.exception("Erreur lors de la récupération des scrims actifs: %s", e)
            return []

    # --- Nouvelles méthodes pour la gestion des équipes ---
    async def is_user_registered_in_any_team(self, scrim_id: int, internal_user_id: int) -> bool:
        info = await self.get_scrim_info(scrim_id)
        if not info:
            return False
        team1 = info.get("team1") or []
        team2 = info.get("team2") or []
        return internal_user_id in team1 or internal_user_id in team2

    async def add_team_participant(self, scrim_id: int, team: str, internal_user_id: int) -> bool:
        info = await self.get_scrim_info(scrim_id)
        if not info or team not in ["team1", "team2"]:
            return False
        current_team = info.get(team) or []
        if internal_user_id in current_team:
            return False
        current_team.append(internal_user_id)
        query = f"UPDATE scrims SET {team} = $1 WHERE id = $2;"
        try:
            await database.execute(query, current_team, scrim_id)
            return True
        except Exception as e:
            logger.error("Erreur lors de l'ajout d'un participant à %s: %s", team, e)
            return False

    async def remove_team_participant(self, scrim_id: int, internal_user_id: int) -> bool:
        info = await self.get_scrim_info(scrim_id)
        if not info:
            return False
        updated = False
        if internal_user_id in (info.get("team1") or []):
            team1 = info.get("team1")
            team1.remove(internal_user_id)
            query = "UPDATE scrims SET team1 = $1 WHERE id = $2;"
            try:
                await database.execute(query, team1, scrim_id)
                updated = True
            except Exception as e:
                logger.error("Erreur lors de la suppression d'un participant de team1: %s", e)
                return False
        if internal_user_id in (info.get("team2") or []):
            team2 = info.get("team2")
            team2.remove(internal_user_id)
            query = "UPDATE scrims SET team2 = $1 WHERE id = $2;"
            try:
                await database.execute(query, team2, scrim_id)
                updated = True
            except Exception as e:
                logger.error("Erreur lors de la suppression d'un participant de team2: %s", e)
                return False
        return updated
