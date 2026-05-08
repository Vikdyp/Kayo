# cogs/reputation/service/profile_service.py

import logging
import re
from typing import Optional, Dict
from utils.database import database
from .reputation_service import get_internal_id

logger = logging.getLogger(__name__)

# Regex pour valider le lien tracker
TRACKER_REGEX = r"^https://tracker\.gg/valorant/profile/riot/.+/overview$"

async def get_user_profile(discord_id: int) -> Dict[str, Optional[str]]:
    """
    Récupère (genre, valorant_tracker, lft, note) depuis la table user_profile.
    Retourne un dict avec ces 4 clés.
    """
    user_id = await get_internal_id(discord_id)
    if user_id is None:
        return {"genre": None, "valorant_tracker": None, "lft": None, "note": None}

    query = """
        SELECT genre, valorant_tracker, lft, note
        FROM user_profile
        WHERE user_id = $1
        LIMIT 1;
    """
    record = await database.fetchrow(query, user_id)
    if not record:
        return {"genre": None, "valorant_tracker": None, "lft": None, "note": None}

    return {
        "genre": record["genre"],
        "valorant_tracker": record["valorant_tracker"],
        "lft": record["lft"],
        "note": record["note"]
    }

async def set_user_profile(
    discord_id: int,
    genre: Optional[str] = None,
    valorant_tracker: Optional[str] = None,
    lft: Optional[str] = None,
    note: Optional[str] = None
) -> bool:
    """
    Met à jour (ou insère) le profil utilisateur dans la table user_profile.
    Valide :
      - Le format du lien tracker
      - L'absence de liens dans "note"
    """
    user_id = await get_internal_id(discord_id)
    if user_id is None:
        logger.debug(f"[set_user_profile] user_id is None pour discord_id={discord_id}")
        return False

    # Validation du lien tracker
    if valorant_tracker:
        if not re.match(TRACKER_REGEX, valorant_tracker):
            logger.debug(f"[set_user_profile] Lien tracker invalide: {valorant_tracker}")
            return False

    # Validation du champ "note" (pas de lien)
    if note:
        # Interdit tout "http" ou "https"
        if re.search(r"https?://", note, re.IGNORECASE):
            logger.debug(f"[set_user_profile] Note contient un lien: {note}")
            return False

    # UPSERT
    query = """
        INSERT INTO user_profile (user_id, genre, valorant_tracker, lft, note)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (user_id)
        DO UPDATE SET
            genre = EXCLUDED.genre,
            valorant_tracker = EXCLUDED.valorant_tracker,
            lft = EXCLUDED.lft,
            note = EXCLUDED.note
    """
    try:
        await database.execute(query, user_id, genre, valorant_tracker, lft, note)
        logger.debug(f"[set_user_profile] Profil mis à jour pour user_id={user_id}")
        return True
    except Exception as e:
        logger.error(f"[set_user_profile] Échec de la mise à jour pour user_id={user_id}: {e}")
        return False