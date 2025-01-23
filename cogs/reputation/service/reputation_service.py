# cogs/reputation/service/reputation_service.py

import logging
from datetime import date
from typing import Dict
from utils.database import database

logger = logging.getLogger("reputation")

async def get_internal_id(discord_id: int) -> int:
    # 1) Tente de récupérer
    query_select = "SELECT id FROM user_id WHERE discord_id = $1;"
    found_id = await database.fetchval(query_select, discord_id)
    if found_id is not None:
        return found_id
    
    # 2) Sinon on l'insère
    query_insert = "INSERT INTO user_id (discord_id) VALUES ($1) RETURNING id;"
    new_id = await database.fetchval(query_insert, discord_id)
    return new_id

async def add_event(reporter_discord_id: int, target_discord_id: int, event_type: str) -> bool:
    """
    Ajoute ou incrémente un événement de réputation (report ou recommendation) dans la base.
    - Limite de 5 actions par reporter/target/event_type (global) + 1 par jour.
    """
    today = date.today()

    # Récupération des IDs internes
    reporter_id = await get_internal_id(reporter_discord_id)
    target_id = await get_internal_id(target_discord_id)
    if reporter_id is None or target_id is None:
        return False

    # Vérifier le total d'actions (max 5)
    query_check_total = """
        SELECT COALESCE(SUM(count), 0)
        FROM reputation_events
        WHERE reporter_id = $1 AND target_id = $2 AND event_type = $3;
    """
    total_count = await database.fetchval(query_check_total, reporter_id, target_id, event_type)
    if total_count and int(total_count) >= 5:
        return False

    # UPSERT (on incrémente de 1 l'événement du jour)
    query_upsert = """
        INSERT INTO reputation_events (reporter_id, target_id, event_type, event_date, count)
        VALUES ($1, $2, $3, $4, 1)
        ON CONFLICT (reporter_id, target_id, event_type, event_date)
        DO UPDATE SET count = reputation_events.count + 1
        RETURNING count;
    """
    new_count = await database.fetchval(query_upsert, reporter_id, target_id, event_type, today)

    # Si ça dépasse 5, on annule
    if new_count and int(new_count) > 5:
        query_decrement = """
            UPDATE reputation_events
            SET count = count - 1
            WHERE reporter_id = $1 AND target_id = $2 AND event_type = $3 AND event_date = $4;
        """
        await database.execute(query_decrement, reporter_id, target_id, event_type, today)
        return False

    return True

async def get_profile_data(target_discord_id: int) -> Dict[str, int]:
    """
    Retourne un dictionnaire avec le nombre total de signalements ("reports")
    et recommandations ("recommendations") reçus par un utilisateur.
    """
    target_id = await get_internal_id(target_discord_id)
    if target_id is None:
        return {"reports": 0, "recommendations": 0}

    query_reports = """
        SELECT COALESCE(SUM(count), 0)
        FROM reputation_events
        WHERE target_id = $1 AND event_type = 'report';
    """
    query_recos = """
        SELECT COALESCE(SUM(count), 0)
        FROM reputation_events
        WHERE target_id = $1 AND event_type = 'recommendation';
    """
    reports_count = await database.fetchval(query_reports, target_id)
    recos_count = await database.fetchval(query_recos, target_id)
    return {
        "reports": int(reports_count or 0),
        "recommendations": int(recos_count or 0)
    }
