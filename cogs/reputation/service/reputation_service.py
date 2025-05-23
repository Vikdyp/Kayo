import logging
from datetime import date
from typing import Dict, Tuple
from utils.database import database

logger = logging.getLogger("reputation")

async def get_internal_id(discord_id: int) -> int:
    query_select = "SELECT id FROM user_id WHERE discord_id = $1;"
    found_id = await database.fetchval(query_select, discord_id)
    if found_id is not None:
        return found_id
    
    query_insert = "INSERT INTO user_id (discord_id) VALUES ($1) RETURNING id;"
    new_id = await database.fetchval(query_insert, discord_id)
    return new_id

async def add_event(reporter_discord_id: int, target_discord_id: int, event_type: str) -> Tuple[bool, str]:
    """
    Ajoute un événement de réputation (report ou recommendation) dans la base.
    - Limite : 1 action par jour pour une paire reporter/target/event_type.
    - Limite globale : 5 actions maximum.
    Retourne un tuple (succès, message) détaillant l'issue.
    """
    today = date.today()

    # Récupération des IDs internes
    reporter_id = await get_internal_id(reporter_discord_id)
    target_id = await get_internal_id(target_discord_id)
    if reporter_id is None or target_id is None:
        return (False, "Erreur interne lors de la récupération des identifiants.")

    # Vérifier si l'action a déjà été effectuée aujourd'hui
    query_check_today = """
        SELECT count
        FROM reputation_events
        WHERE reporter_id = $1 AND target_id = $2 AND event_type = $3 AND event_date = $4;
    """
    today_count = await database.fetchval(query_check_today, reporter_id, target_id, event_type, today)
    if today_count and int(today_count) >= 1:
        if event_type == 'report':
            return (False, "Vous avez déjà signalé cet utilisateur aujourd'hui.")
        else:
            return (False, "Vous avez déjà recommandé cet utilisateur aujourd'hui.")

    # Vérifier le total global d'actions
    query_check_total = """
        SELECT COALESCE(SUM(count), 0)
        FROM reputation_events
        WHERE reporter_id = $1 AND target_id = $2 AND event_type = $3;
    """
    total_count = await database.fetchval(query_check_total, reporter_id, target_id, event_type)
    if total_count and int(total_count) >= 5:
        if event_type == 'report':
            return (False, "La limite globale de signalements pour cet utilisateur est atteinte.")
        else:
            return (False, "La limite globale de recommandations pour cet utilisateur est atteinte.")

    # Insérer l'événement pour aujourd'hui
    query_insert = """
        INSERT INTO reputation_events (reporter_id, target_id, event_type, event_date, count)
        VALUES ($1, $2, $3, $4, 1)
        RETURNING count;
    """
    new_count = await database.fetchval(query_insert, reporter_id, target_id, event_type, today)
    if new_count is not None and int(new_count) == 1:
        if event_type == 'report':
            return (True, "Signalement enregistré avec succès.")
        else:
            return (True, "Recommandation enregistrée avec succès.")

    return (False, "Une erreur est survenue lors de l'enregistrement de votre action.")

async def get_profile_data(target_discord_id: int) -> Dict[str, int]:
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
