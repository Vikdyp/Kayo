import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from utils.database import database
import logging

from utils.base import (
    get_or_create_server_record,
    store_persistent_message,
    get_persistent_message,
    delete_persistent_message,
)
logger = logging.getLogger(__name__)

# Les rangs Valorant de base
RANGS_VALORANT = (
    'fer', 'bronze', 'argent', 'or', 'platine',
    'diamant', 'ascendant', 'immortel', 'radiant', 'no_rank'
)

# ------------------------------------------------
# NOUVEAU : get_user_pk_by_discord_id
# ------------------------------------------------
async def get_user_pk_by_discord_id(discord_id: int) -> Optional[int]:
    """
    Retourne l'ID (PK) de la table user_id pour un discord_id donné.
    """
    query = """
        SELECT id
          FROM user_id
         WHERE discord_id = $1
         LIMIT 1
    """
    record = await database.fetchrow(query, discord_id)
    if record:
        return record["id"]
    return None


# ------------------------------------------------
# CHANNEL CONFIG
# ------------------------------------------------
async def get_channel_id(guild_id: int, action: str) -> Optional[int]:
    """
    Récupère channel_id depuis channel_configurations,
    en passant par la table serveur_id (server_db_id).
    """
    server_db_id = await get_or_create_server_record(guild_id, "Inconnu")
    if not server_db_id:
        return None

    query = """
        SELECT channel_id
        FROM channel_configurations
        WHERE server_id = $1 AND action = $2;
    """
    try:
        channel_id = await database.fetchval(query, server_db_id, action)
        if channel_id:
            logger.debug(f"Salon trouvé: server_db_id={server_db_id}, action={action}, channel_id={channel_id}")
        else:
            logger.warning(f"Aucun salon trouvé pour server_db_id={server_db_id} et action='{action}'.")
        return channel_id
    except Exception as e:
        logger.error(f"[get_channel_id] Erreur : {e}")
        return None

async def set_channel_id(guild_id: int, action: str, channel_id: int) -> bool:
    """
    Définit (ou met à jour) le channel_id pour une action donnée dans la table channel_configurations,
    après avoir récupéré l'ID interne du serveur via get_or_create_server_record.
    """
    server_db_id = await get_or_create_server_record(guild_id, "Inconnu")
    if not server_db_id:
        return False

    query = """
        INSERT INTO channel_configurations (server_id, action, channel_id)
        VALUES ($1, $2, $3)
        ON CONFLICT (server_id, action) DO UPDATE
        SET channel_id = EXCLUDED.channel_id;
    """
    try:
        await database.execute(query, server_db_id, action, channel_id)
        logger.info(f"Salon défini: server_db_id={server_db_id}, action='{action}', channel_id={channel_id}")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de la définition du salon : {e}")
        return False

# ------------------------------------------------
# USER VALORANT INFO (NOUVELLE TABLE : valorant_info)
# ------------------------------------------------
async def update_user_valorant_info(discord_id: int, pseudo: str, tag: str) -> bool:
    """
    Met à jour le pseudo et le tag Valorant dans valorant_info,
    après avoir récupéré user_id (PK) depuis la table user_id.
    """
    user_pk = await get_user_pk_by_discord_id(discord_id)
    if not user_pk:
        logger.warning(f"[update_user_valorant_info] Impossible de trouver user_id pour discord_id={discord_id}.")
        return False

    query = """
        INSERT INTO valorant_info (user_id, pseudo, tag, last_notification)
        VALUES ($1, $2, $3, NULL)
        ON CONFLICT (user_id)
        DO UPDATE SET pseudo = EXCLUDED.pseudo,
                      tag    = EXCLUDED.tag,
                      puuid  = NULL,
                      region = NULL,
                      last_notification = NULL;
    """
    try:
        await database.execute(query, user_pk, pseudo, tag)
        logger.info(f"Informations Valorant mises à jour pour Discord ID {discord_id}: {pseudo}#{tag}")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de la mise à jour des informations Valorant pour Discord ID {discord_id}: {e}")
        return False

async def set_valorant_details(discord_id: int, puuid: str, region: str, rank: str, elo: int) -> bool:
    """
    Met à jour le puuid, la region, le rank et l'elo dans valorant_info.
    """
    user_pk = await get_user_pk_by_discord_id(discord_id)
    if not user_pk:
        logger.warning(f"[set_valorant_details] Impossible de trouver user_id pour discord_id={discord_id}.")
        return False

    query = """
        UPDATE valorant_info
           SET puuid  = $1,
               region = $2,
               rank   = $3,
               elo    = $4
         WHERE user_id = $5
    """
    try:
        await database.execute(query, puuid, region, rank, elo, user_pk)
        logger.info(f"Détails Valorant mis à jour pour Discord ID {discord_id}: PUUID={puuid}, Région={region}, Rang={rank}, Elo={elo}")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de la mise à jour des détails Valorant pour Discord ID {discord_id}: {e}")
        return False

async def get_all_users_with_valo_info() -> List[Dict]:
    """
    Récupère tous les utilisateurs ayant pseudo/tag non NULL dans valorant_info,
    en jointure avec user_id pour obtenir leur discord_id.
    """
    query = """
        SELECT u.discord_id,
               v.pseudo  AS valorant_pseudo,
               v.tag     AS valorant_tag,
               v.puuid   AS valorant_puuid,
               v.region  AS valorant_region,
               v.rank    AS valorant_rank,
               v.elo     AS valorant_elo
          FROM user_id u
          JOIN valorant_info v ON u.id = v.user_id
         WHERE v.pseudo IS NOT NULL
           AND v.tag    IS NOT NULL
    """
    try:
        records = await database.fetch(query)
        logger.info(f"{len(records)} utilisateurs récupérés pour la mise à jour Valorant.")
        return records
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des utilisateurs pour la mise à jour Valorant: {e}")
        return []

async def get_user_by_pseudo_tag(pseudo: str, tag: str) -> Optional[int]:
    """
    Vérifie si un pseudo + tag est déjà enregistré dans valorant_info.
    Retourne le discord_id associé ou None si pas de doublon.
    """
    query = """
        SELECT u.discord_id
          FROM valorant_info v
          JOIN user_id u ON v.user_id = u.id
         WHERE v.pseudo = $1
           AND v.tag    = $2
         LIMIT 1
    """
    try:
        record = await database.fetchrow(query, pseudo, tag)
        if record:
            logger.info(f"Doublon trouvé pour {pseudo}#{tag} avec Discord ID {record['discord_id']}.")
            return record["discord_id"]
        else:
            logger.info(f"Aucun doublon trouvé pour {pseudo}#{tag}.")
            return None
    except Exception as e:
        logger.error(f"[get_user_by_pseudo_tag] Erreur : {e}")
        return None

# ------------------------------------------------
# SUPPRIMER DONNÉES VALORANT
# ------------------------------------------------
async def delete_valo_data(discord_id: int) -> bool:
    """
    Supprime (ou met à NULL) les données Valorant dans valorant_info.
    Ici on fait un DELETE complet de la ligne.
    """
    user_pk = await get_user_pk_by_discord_id(discord_id)
    if not user_pk:
        logger.warning(f"[delete_valo_data] user_id introuvable pour discord_id={discord_id}.")
        return False

    query = """
        DELETE FROM valorant_info
         WHERE user_id = $1
    """
    try:
        await database.execute(query, user_pk)
        logger.info(f"Données Valorant supprimées pour Discord ID {discord_id}.")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de la suppression des données Valorant pour {discord_id}: {e}")
        return False

async def user_exists_in_db(discord_id: int) -> bool:
    """
    Vérifie l'existence d'un enregistrement dans la table user_id pour ce discord_id.
    """
    query = """
        SELECT 1
          FROM user_id
         WHERE discord_id = $1
         LIMIT 1
    """
    record = await database.fetchrow(query, discord_id)
    return record is not None

async def valorant_account_linked(discord_id: int) -> bool:
    """Vérifie si l'utilisateur possède une entrée dans `valorant_info` (quel que soit le contenu de puuid)."""
    user_pk = await get_user_pk_by_discord_id(discord_id)
    if not user_pk:
        return False

    query = """
        SELECT 1
          FROM valorant_info
         WHERE user_id = $1
         LIMIT 1
    """
    record = await database.fetchrow(query, user_pk)
    return record is not None


async def valorant_puuid_present(discord_id: int) -> bool:
    """Vérifie que l'utilisateur est dans `valorant_info` ET que le champ puuid n'est pas NULL."""
    user_pk = await get_user_pk_by_discord_id(discord_id)
    if not user_pk:
        return False

    query = """
        SELECT puuid
          FROM valorant_info
         WHERE user_id = $1
         LIMIT 1
    """
    record = await database.fetchrow(query, user_pk)
    # record peut être None (pas de ligne) ou {"puuid": None} si le PUUID n'est pas encore récupéré
    return (record is not None) and (record["puuid"] is not None)

# ------------------------------------------------
# RÔLES : gestion + cache local
# ------------------------------------------------
_role_cache: Dict[int, Dict[str, int]] = {}
_role_cache_lock = asyncio.Lock()

async def get_role_id_for_config(guild_id: int, guild_name: str, role_config_pk: int) -> Optional[int]:
    """
    Récupère le 'role_id' (ID Discord du rôle) dans la table roles_configurations,
    basé sur la PK `id` (role_config_pk) et l'ID interne du serveur.
    """
    server_db_id = await get_or_create_server_record(guild_id, guild_name)
    if not server_db_id:
        return None

    query = """
        SELECT role_id
        FROM roles_configurations
        WHERE server_id = $1
          AND id = $2
    """
    try:
        record = await database.fetchrow(query, server_db_id, role_config_pk)
        if record:
            return record["role_id"]
        else:
            return None
    except Exception as e:
        logger.error(f"[get_role_id_for_config] Erreur : {e}")
        return None

async def get_role_mappings(guild_id: int, guild_name: str) -> Optional[Dict[str, int]]:
    """
    Récupère (depuis la table roles_configurations) les mappings pour les noms de rang Valorant
    -> role_id (ID Discord), en filtrant sur RANGS_VALORANT.
    On utilise server_id (= PK dans serveur_id).
    """
    async with _role_cache_lock:
        if guild_id in _role_cache:
            logger.debug(f"Récupération des mappings de rôles pour guild_id={guild_id} depuis le cache.")
            return _role_cache[guild_id]

    server_db_id = await get_or_create_server_record(guild_id, guild_name)
    if not server_db_id:
        return None

    placeholders = ', '.join(f"'{r}'" for r in RANGS_VALORANT)
    query = f"""
        SELECT role_name, role_id
          FROM roles_configurations
         WHERE server_id = $1
           AND role_name IN ({placeholders});
    """
    try:
        records = await database.fetch(query, server_db_id)
        if not records:
            logger.warning(f"Aucun rôle de rang Valorant trouvé pour server_id={server_db_id}.")
            return None

        role_mappings = {r['role_name'].lower(): r['role_id'] for r in records}

        async with _role_cache_lock:
            _role_cache[guild_id] = role_mappings
            logger.info(f"Mappings de rôles Valorant pour guild_id={guild_id} mis en cache.")
        return role_mappings

    except Exception as e:
        logger.error(f"Erreur lors de la récupération des configurations de rôles pour guild_id={guild_id}: {e}")
        return None

async def refresh_role_mappings(guild_id: int, guild_name: str):
    async with _role_cache_lock:
        if guild_id in _role_cache:
            del _role_cache[guild_id]
            logger.info(f"Cache des mappings de rôles vidé pour guild_id={guild_id}.")
    await get_role_mappings(guild_id, guild_name)

# ------------------------------------------------
# FLAGS DE MISE À JOUR (DEPRECATED - remplacées par le pipeline)
# ------------------------------------------------
# Les fonctions suivantes ont été supprimées car elles utilisaient
# la colonne 'needs_update' qui n'existe plus:
# - get_users_with_update_flag_false() -> remplacée par get_users_for_pipeline()
# - mark_user_update_flag_true() -> remplacée par update_pipeline_success/error()
# - reset_all_update_flag_false() -> plus nécessaire avec last_checked_at

# ------------------------------------------------
# PERSISTENCE DE LA NOTIFICATION
# ------------------------------------------------
async def get_last_notification(discord_id: int) -> Optional[datetime]:
    """
    Récupère le timestamp de la dernière notification envoyée à l'utilisateur.
    """
    user_pk = await get_user_pk_by_discord_id(discord_id)
    if not user_pk:
        return None
    query = """
        SELECT last_notification
          FROM valorant_info
         WHERE user_id = $1
         LIMIT 1
    """
    record = await database.fetchrow(query, user_pk)
    if record:
        return record.get("last_notification")
    return None

async def update_last_notification(discord_id: int, timestamp: datetime) -> bool:
    """
    Met à jour le timestamp de la dernière notification envoyée pour l'utilisateur.
    """
    user_pk = await get_user_pk_by_discord_id(discord_id)
    if not user_pk:
        return False
    query = """
        UPDATE valorant_info
           SET last_notification = $1
         WHERE user_id = $2
    """
    try:
        await database.execute(query, timestamp, user_pk)
        return True
    except Exception as e:
        logger.error(f"Erreur lors de la mise à jour de last_notification pour discord_id {discord_id}: {e}")
        return False

# ------------------------------------------------
# GESTION DES UTILISATEURS INACTIFS
# ------------------------------------------------
async def mark_user_inactive(discord_id: int) -> bool:
    """
    Marque un utilisateur comme inactif quand il quitte tous les serveurs.
    Préserve ses données mais l'exclut des cycles de mise à jour.
    """
    user_pk = await get_user_pk_by_discord_id(discord_id)
    if not user_pk:
        return False

    query = """
        UPDATE valorant_info
           SET is_active = FALSE,
               deactivated_at = NOW()
         WHERE user_id = $1
           AND is_active = TRUE
    """
    try:
        await database.execute(query, user_pk)
        logger.info(f"[mark_user_inactive] Discord ID {discord_id} marqué comme inactif.")
        return True
    except Exception as e:
        logger.error(f"[mark_user_inactive] Erreur pour discord_id={discord_id}: {e}")
        return False


async def reactivate_user(discord_id: int) -> bool:
    """
    Réactive un utilisateur précédemment inactif quand il rejoint un serveur.
    """
    user_pk = await get_user_pk_by_discord_id(discord_id)
    if not user_pk:
        return False

    query = """
        UPDATE valorant_info
           SET is_active = TRUE,
               deactivated_at = NULL,
               last_checked_at = NULL,
               error_count = 0
         WHERE user_id = $1
           AND is_active = FALSE
    """
    try:
        result = await database.execute(query, user_pk)
        # Vérifie si une ligne a été modifiée
        if "UPDATE 0" not in str(result):
            logger.info(f"[reactivate_user] Discord ID {discord_id} réactivé.")
            return True
        return False
    except Exception as e:
        logger.error(f"[reactivate_user] Erreur pour discord_id={discord_id}: {e}")
        return False


async def is_user_active(discord_id: int) -> bool:
    """
    Vérifie si un utilisateur est actif (présent dans au moins un serveur).
    """
    user_pk = await get_user_pk_by_discord_id(discord_id)
    if not user_pk:
        return False

    query = """
        SELECT is_active
          FROM valorant_info
         WHERE user_id = $1
         LIMIT 1
    """
    record = await database.fetchrow(query, user_pk)
    if record:
        return record.get("is_active", True)
    return False


async def get_inactive_users_count() -> int:
    """
    Retourne le nombre d'utilisateurs inactifs pour le monitoring.
    """
    query = "SELECT COUNT(*) FROM valorant_info WHERE is_active = FALSE"
    try:
        return await database.fetchval(query) or 0
    except Exception as e:
        logger.error(f"[get_inactive_users_count] Erreur: {e}")
        return 0


async def get_user_stats() -> Dict[str, int]:
    """
    Retourne des statistiques sur les utilisateurs Valorant pour le monitoring.
    """
    query = """
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE is_active = TRUE) AS active,
            COUNT(*) FILTER (WHERE is_active = FALSE) AS inactive,
            COUNT(*) FILTER (WHERE puuid IS NOT NULL) AS with_puuid,
            COUNT(*) FILTER (WHERE tracking_enabled = TRUE) AS tracking_enabled
        FROM valorant_info
    """
    try:
        record = await database.fetchrow(query)
        if record:
            return {
                "total": record["total"] or 0,
                "active": record["active"] or 0,
                "inactive": record["inactive"] or 0,
                "with_puuid": record["with_puuid"] or 0,
                "tracking_enabled": record["tracking_enabled"] or 0
            }
        return {"total": 0, "active": 0, "inactive": 0, "with_puuid": 0, "tracking_enabled": 0}
    except Exception as e:
        logger.error(f"[get_user_stats] Erreur: {e}")
        return {"total": 0, "active": 0, "inactive": 0, "with_puuid": 0, "tracking_enabled": 0}


async def validate_valorant_info_integrity() -> List[Dict]:
    """
    Vérifie l'intégrité des données Valorant et retourne les anomalies.
    Utile pour le debugging et la maintenance.
    """
    anomalies = []

    # Utilisateurs avec pseudo/tag mais sans puuid depuis plus de 24h
    query_missing_puuid = """
        SELECT u.discord_id, v.pseudo, v.tag
        FROM valorant_info v
        JOIN user_id u ON u.id = v.user_id
        WHERE v.puuid IS NULL
          AND v.pseudo IS NOT NULL
          AND v.tag IS NOT NULL
          AND v.is_active = TRUE
    """
    try:
        records = await database.fetch(query_missing_puuid)
        for r in records:
            anomalies.append({
                "type": "missing_puuid",
                "discord_id": r["discord_id"],
                "pseudo": r["pseudo"],
                "tag": r["tag"]
            })
    except Exception as e:
        logger.error(f"[validate_valorant_info_integrity] Erreur missing_puuid: {e}")

    # Utilisateurs inactifs depuis plus de 30 jours
    query_long_inactive = """
        SELECT u.discord_id, v.deactivated_at
        FROM valorant_info v
        JOIN user_id u ON u.id = v.user_id
        WHERE v.is_active = FALSE
          AND v.deactivated_at < NOW() - INTERVAL '30 days'
    """
    try:
        records = await database.fetch(query_long_inactive)
        for r in records:
            anomalies.append({
                "type": "long_inactive",
                "discord_id": r["discord_id"],
                "deactivated_at": str(r["deactivated_at"])
            })
    except Exception as e:
        logger.error(f"[validate_valorant_info_integrity] Erreur long_inactive: {e}")

    return anomalies


async def bulk_mark_inactive(discord_ids: List[int]) -> int:
    """
    Marque plusieurs utilisateurs comme inactifs en une seule opération.
    Retourne le nombre d'utilisateurs marqués.
    """
    if not discord_ids:
        return 0

    query = """
        UPDATE valorant_info v
           SET is_active = FALSE,
               deactivated_at = NOW()
          FROM user_id u
         WHERE u.id = v.user_id
           AND u.discord_id = ANY($1)
           AND v.is_active = TRUE
    """
    try:
        result = await database.execute(query, discord_ids)
        # Parse le résultat pour obtenir le nombre de lignes affectées
        if result:
            count = int(result.split()[-1]) if result.split()[-1].isdigit() else 0
            logger.info(f"[bulk_mark_inactive] {count} utilisateurs marqués inactifs.")
            return count
        return 0
    except Exception as e:
        logger.error(f"[bulk_mark_inactive] Erreur: {e}")
        return 0


async def cleanup_old_inactive_users(days: int = 180) -> int:
    """
    Supprime les données des utilisateurs inactifs depuis plus de X jours.
    ATTENTION: Cette opération est irréversible.

    Args:
        days: Nombre de jours d'inactivité avant suppression (défaut: 180)

    Returns:
        Nombre d'utilisateurs supprimés
    """
    if days < 30:
        logger.warning(f"[cleanup_old_inactive_users] Refus de supprimer avec days={days} (minimum 30)")
        return 0

    query = """
        DELETE FROM valorant_info v
        USING user_id u
        WHERE u.id = v.user_id
          AND v.is_active = FALSE
          AND v.deactivated_at < NOW() - INTERVAL '%s days'
        RETURNING u.discord_id
    """ % days  # Note: days est validé ci-dessus, pas d'injection possible
    try:
        records = await database.fetch(query)
        count = len(records)
        if count > 0:
            logger.info(f"[cleanup_old_inactive_users] {count} utilisateurs supprimés (inactifs > {days} jours).")
        return count
    except Exception as e:
        logger.error(f"[cleanup_old_inactive_users] Erreur: {e}")
        return 0


# ------------------------------------------------
# PIPELINE FUNCTIONS (new time-based scheduling)
# ------------------------------------------------

async def get_users_for_pipeline(limit: int = 50) -> List[Dict]:
    """
    Récupère les utilisateurs pour le pipeline, ordonnés par last_checked_at.
    Les utilisateurs jamais vérifiés (NULL) sont prioritaires.
    Seuls les utilisateurs actifs avec pseudo/tag sont retournés.

    Args:
        limit: Nombre maximum d'utilisateurs à retourner

    Returns:
        Liste de dictionnaires avec les infos utilisateur
    """
    query = """
        SELECT u.discord_id,
               v.pseudo  AS valorant_pseudo,
               v.tag     AS valorant_tag,
               v.puuid   AS valorant_puuid,
               v.region  AS valorant_region,
               v.platform AS valorant_platform,
               v.rank    AS valorant_rank,
               v.elo     AS valorant_elo,
               v.error_count,
               v.last_error_at
          FROM valorant_info v
          JOIN user_id u ON u.id = v.user_id
         WHERE v.is_active = TRUE
           AND v.pseudo IS NOT NULL
           AND v.tag    IS NOT NULL
         ORDER BY v.last_checked_at ASC NULLS FIRST
         LIMIT $1
    """
    try:
        records = await database.fetch(query, limit)
        logger.debug(f"[get_users_for_pipeline] {len(records)} utilisateurs récupérés")
        return records
    except Exception as e:
        logger.error(f"[get_users_for_pipeline] Erreur: {e}")
        return []


async def update_pipeline_success(
    discord_id: int,
    puuid: Optional[str] = None,
    region: Optional[str] = None,
    platform: Optional[str] = None,
    rank: Optional[str] = None,
    elo: Optional[int] = None
) -> bool:
    """
    Met à jour un utilisateur après une étape pipeline réussie.
    Reset error_count à 0 et met last_checked_at à NOW().

    Args:
        discord_id: ID Discord de l'utilisateur
        puuid, region, platform, rank, elo: Champs optionnels à mettre à jour

    Returns:
        True si succès, False sinon
    """
    user_pk = await get_user_pk_by_discord_id(discord_id)
    if not user_pk:
        logger.warning(f"[update_pipeline_success] user_pk introuvable pour discord_id={discord_id}")
        return False

    # Construire la requête dynamiquement selon les champs fournis
    updates = ["last_checked_at = NOW()", "error_count = 0", "last_error_at = NULL"]
    params = []
    param_idx = 1

    if puuid is not None:
        updates.append(f"puuid = ${param_idx}")
        params.append(puuid)
        param_idx += 1

    if region is not None:
        updates.append(f"region = ${param_idx}")
        params.append(region)
        param_idx += 1

    if platform is not None:
        updates.append(f"platform = ${param_idx}")
        params.append(platform)
        param_idx += 1

    if rank is not None:
        updates.append(f"rank = ${param_idx}")
        params.append(rank)
        param_idx += 1

    if elo is not None:
        updates.append(f"elo = ${param_idx}")
        params.append(elo)
        param_idx += 1

    params.append(user_pk)

    query = f"""
        UPDATE valorant_info
           SET {', '.join(updates)}
         WHERE user_id = ${param_idx}
    """

    try:
        await database.execute(query, *params)
        logger.debug(f"[update_pipeline_success] Mis à jour discord_id={discord_id}")
        return True
    except Exception as e:
        logger.error(f"[update_pipeline_success] Erreur pour discord_id={discord_id}: {e}")
        return False


async def update_pipeline_error(discord_id: int) -> bool:
    """
    Met à jour un utilisateur après une erreur pipeline.
    Incrémente error_count et met last_error_at et last_checked_at à NOW().

    Args:
        discord_id: ID Discord de l'utilisateur

    Returns:
        True si succès, False sinon
    """
    user_pk = await get_user_pk_by_discord_id(discord_id)
    if not user_pk:
        logger.warning(f"[update_pipeline_error] user_pk introuvable pour discord_id={discord_id}")
        return False

    query = """
        UPDATE valorant_info
           SET error_count = error_count + 1,
               last_error_at = NOW(),
               last_checked_at = NOW()
         WHERE user_id = $1
    """

    try:
        await database.execute(query, user_pk)
        logger.debug(f"[update_pipeline_error] error_count incrémenté pour discord_id={discord_id}")
        return True
    except Exception as e:
        logger.error(f"[update_pipeline_error] Erreur pour discord_id={discord_id}: {e}")
        return False


async def reset_user_for_account_change(discord_id: int, new_pseudo: str, new_tag: str) -> bool:
    """
    Reset complet des données Valorant lors d'un changement de compte.
    Conserve is_active et tracking_enabled, reset tout le reste.

    Args:
        discord_id: ID Discord de l'utilisateur
        new_pseudo: Nouveau pseudo Valorant
        new_tag: Nouveau tag Valorant

    Returns:
        True si succès, False sinon
    """
    user_pk = await get_user_pk_by_discord_id(discord_id)
    if not user_pk:
        logger.warning(f"[reset_user_for_account_change] user_pk introuvable pour discord_id={discord_id}")
        return False

    query = """
        UPDATE valorant_info
           SET pseudo = $1,
               tag = $2,
               puuid = NULL,
               region = NULL,
               platform = NULL,
               rank = NULL,
               elo = NULL,
               error_count = 0,
               last_error_at = NULL,
               last_checked_at = NULL,
               last_notification = NULL
         WHERE user_id = $3
    """

    try:
        await database.execute(query, new_pseudo, new_tag, user_pk)
        logger.info(f"[reset_user_for_account_change] Reset pour discord_id={discord_id}, nouveau compte: {new_pseudo}#{new_tag}")
        return True
    except Exception as e:
        logger.error(f"[reset_user_for_account_change] Erreur pour discord_id={discord_id}: {e}")
        return False


async def get_all_valorant_discord_ids() -> List[int]:
    """
    Récupère tous les discord_id ayant un compte Valorant lié.
    Utilisé pour le startup sync.

    Returns:
        Liste des discord_id
    """
    query = """
        SELECT u.discord_id
          FROM valorant_info v
          JOIN user_id u ON u.id = v.user_id
         WHERE v.pseudo IS NOT NULL
           AND v.tag IS NOT NULL
    """
    try:
        records = await database.fetch(query)
        return [r["discord_id"] for r in records]
    except Exception as e:
        logger.error(f"[get_all_valorant_discord_ids] Erreur: {e}")
        return []
