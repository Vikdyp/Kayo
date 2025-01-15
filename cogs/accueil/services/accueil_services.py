#cogs\accueil\services\accueil_services.py
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo
from utils.database import database
import logging

logger = logging.getLogger("accueil.services")

def get_local_datetime():
    paris_tz = ZoneInfo("Europe/Paris")
    return datetime.now(paris_tz)

async def get_welcome_channel_id(guild_id: int) -> Optional[int]:
    server_id = await get_server_id(guild_id)
    if server_id is None:
        return None

    query = """
        SELECT channel_id 
        FROM channel_configurations 
        WHERE server_id = $1 AND action = 'welcome';
    """
    return await database.fetchval(query, server_id)

async def get_channel_ids(guild_id: int, actions: list) -> Dict[str, int]:
    server_id = await get_server_id(guild_id)
    if server_id is None:
        return {}
    query = """
        SELECT action, channel_id 
        FROM channel_configurations 
        WHERE server_id = $1 AND action = ANY($2::text[]);
    """
    records = await database.fetch(query, server_id, actions)
    return {record['action']: record['channel_id'] for record in records}

async def get_server_id(guild_id: int) -> Optional[int]:
    query = """
        SELECT id 
        FROM serveur_id 
        WHERE guild_id = $1;
    """
    return await database.fetchval(query, guild_id)

# =========================
# Suivi des membres en BDD
# =========================

async def ensure_today_member_stats(guild_id: int) -> None:
    server_id = await get_server_id(guild_id)
    if server_id is None:
        return
    
    # Utilisation explicite de la date locale
    paris_tz = ZoneInfo("Europe/Paris")
    today = datetime.now(paris_tz).date()

    logger.debug(f"ensure_today_member_stats - Vérification pour la date : {today}")
    query_select = """
        SELECT 1 FROM member_daily_stats
        WHERE guild_id = $1 AND date = $2;
    """
    record = await database.fetchrow(query_select, server_id, today)
    if record:
        logger.debug(f"Entrée trouvée pour la date {today} et guild_id {guild_id}.")
    else:
        logger.debug(f"Aucune entrée trouvée pour la date {today} et guild_id {guild_id}, création en cours.")
        query_insert = """
            INSERT INTO member_daily_stats (guild_id, date, join_count, leave_count)
            VALUES ($1, $2, 0, 0);
        """
        await database.execute(query_insert, server_id, today)

async def log_member_event_aggregated(guild_id: int, event_type: str) -> None:
    server_id = await get_server_id(guild_id)
    if server_id is None:
        return
    
    paris_tz = ZoneInfo("Europe/Paris")
    today = datetime.now(paris_tz).date()

    await ensure_today_member_stats(guild_id)
    query_select = """
        SELECT join_count, leave_count
        FROM member_daily_stats
        WHERE guild_id = $1 AND date = $2;
    """
    record = await database.fetchrow(query_select, server_id, today)
    if record is None:
        if event_type == "join":
            query_insert = """
                INSERT INTO member_daily_stats (guild_id, date, join_count, leave_count)
                VALUES ($1, $2, 1, 0);
            """
        else:
            query_insert = """
                INSERT INTO member_daily_stats (guild_id, date, join_count, leave_count)
                VALUES ($1, $2, 0, 1);
            """
        await database.execute(query_insert, server_id, today)
    else:
        if event_type == "join":
            new_join_count = record['join_count'] + 1
            query_update = """
                UPDATE member_daily_stats
                SET join_count = $3
                WHERE guild_id = $1 AND date = $2;
            """
            await database.execute(query_update, server_id, today, new_join_count)
        else:
            new_leave_count = record['leave_count'] + 1
            query_update = """
                UPDATE member_daily_stats
                SET leave_count = $3
                WHERE guild_id = $1 AND date = $2;
            """
            await database.execute(query_update, server_id, today, new_leave_count)

async def get_aggregated_stats(guild_id: int) -> dict:
    server_id = await get_server_id(guild_id)
    if server_id is None:
        return {
            "join_24h": 0, "leave_24h": 0,
            "join_7d": 0, "leave_7d": 0,
            "join_30d": 0, "leave_30d": 0,
            "total_join": 0, "total_left": 0,
            "join_leave_ratio": 0
        }
    await ensure_today_member_stats(guild_id)
    query_24h = """
        SELECT COALESCE(SUM(join_count), 0) AS join_24h,
               COALESCE(SUM(leave_count), 0) AS leave_24h
        FROM member_daily_stats
        WHERE guild_id = $1 AND date >= (CURRENT_DATE - 1);
    """
    query_7d = """
        SELECT COALESCE(SUM(join_count), 0) AS join_7d,
               COALESCE(SUM(leave_count), 0) AS leave_7d
        FROM member_daily_stats
        WHERE guild_id = $1 AND date >= (CURRENT_DATE - 7);
    """
    query_30d = """
        SELECT COALESCE(SUM(join_count), 0) AS join_30d,
               COALESCE(SUM(leave_count), 0) AS leave_30d
        FROM member_daily_stats
        WHERE guild_id = $1 AND date >= (CURRENT_DATE - 30);
    """
    query_total = """
        SELECT COALESCE(SUM(join_count), 0) AS total_join,
               COALESCE(SUM(leave_count), 0) AS total_left
        FROM member_daily_stats
        WHERE guild_id = $1;
    """
    rec_24h = await database.fetchrow(query_24h, server_id)
    rec_7d  = await database.fetchrow(query_7d, server_id)
    rec_30d = await database.fetchrow(query_30d, server_id)
    rec_total = await database.fetchrow(query_total, server_id)

    join_24h = rec_24h["join_24h"]
    leave_24h = rec_24h["leave_24h"]
    join_7d = rec_7d["join_7d"]
    leave_7d = rec_7d["leave_7d"]
    join_30d = rec_30d["join_30d"]
    leave_30d = rec_30d["leave_30d"]
    total_join = rec_total["total_join"]
    total_left = rec_total["total_left"]
    ratio = float(total_join) if total_left == 0 else round(total_join / total_left, 2)
    return {
        "join_24h": join_24h,
        "leave_24h": leave_24h,
        "join_7d": join_7d,
        "leave_7d": leave_7d,
        "join_30d": join_30d,
        "leave_30d": leave_30d,
        "total_join": total_join,
        "total_left": total_left,
        "join_leave_ratio": ratio,
    }

async def get_member_evolution(guild_id: int, days: int = 30) -> List[Dict]:
    server_id = await get_server_id(guild_id)
    if server_id is None:
        return []
    query = """
        SELECT date, join_count, leave_count
        FROM member_daily_stats
        WHERE guild_id = $1 AND date >= (CURRENT_DATE - $2::integer)
        ORDER BY date ASC;
    """
    records = await database.fetch(query, server_id, days)
    return [dict(record) for record in records]

# =========================
# Fonctions de persistance pour les messages
# =========================

async def get_persistent_message(guild_id: int, message_type: str) -> Optional[Tuple[int, int]]:
    """
    Récupère (channel_id, message_id) pour un message persistant dans 'persistent_messages'.
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
        row = await database.fetchrow(query, server_id, message_type)
        if row:
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
        await database.execute(query, server_id, message_type, channel_id, message_id, requester_id)
        logger.info(f"Message persistant '{message_type}' sauvegardé pour guild {discord_guild_id}.")
    except Exception as e:
        logger.error(f"Erreur save_persistent_message: {e}")
