# cogs/ranking/services/assign_rank_service.py

import asyncio
from typing import Optional, Dict, List
from utils.database import database
import logging

logger = logging.getLogger("rank_service")

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
# NOUVEAU : get_or_create_server_record
# ------------------------------------------------
async def get_or_create_server_record(guild_id: int, guild_name: str) -> Optional[int]:
    """
    Récupère l'ID interne (PK) de la table serveur_id pour un guild_id donné.
    Si le serveur n'existe pas déjà, il est créé.
    """
    try:
        select_query = """
        SELECT id
        FROM serveur_id
        WHERE guild_id = $1
        """
        record = await database.fetchrow(select_query, guild_id)
        if record:
            return record['id']

        insert_query = """
        INSERT INTO serveur_id (guild_id, serveur)
        VALUES ($1, $2)
        RETURNING id;
        """
        new_id = await database.fetchval(insert_query, guild_id, guild_name)
        logger.info(f"[get_or_create_server_record] Serveur créé pour guild_id={guild_id}, id={new_id}")
        return new_id
    except Exception as e:
        logger.error(f"[get_or_create_server_record] Erreur : {e}")
        return None


# ------------------------------------------------
# PERSISTENT MESSAGES
# ------------------------------------------------
async def store_persistent_message(discord_guild_id: int, channel_id: int, message_id: int, message_type: str, guild_name: str = "Inconnu") -> bool:
    """
    Enregistre ou met à jour un message persistant pour un serveur donné.
    Désormais, on récupère d'abord l'ID interne du serveur (server_db_id),
    puis on insère/MAJ dans persistent_messages (colonne guild_id = server_db_id).
    """
    try:
        server_db_id = await get_or_create_server_record(discord_guild_id, guild_name)
        if not server_db_id:
            return False

        query = """
            INSERT INTO persistent_messages (guild_id, channel_id, message_id, message_type)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id, message_type) DO UPDATE
            SET channel_id = EXCLUDED.channel_id,
                message_id = EXCLUDED.message_id,
                created_at = now();
        """
        await database.execute(query, server_db_id, channel_id, message_id, message_type)
        logger.info(
            f"Message persistant stocké: server_db_id={server_db_id}, "
            f"channel_id={channel_id}, message_id={message_id}, type={message_type}"
        )
        return True
    except Exception as e:
        logger.error(f"Erreur lors du stockage du message persistant: {e}")
        return False

async def get_persistent_message(discord_guild_id: int, message_type: str, guild_name: str = "Inconnu") -> Optional[Dict[str, int]]:
    """
    Récupère channel_id et message_id pour un type de message persistant.
    On convertit d'abord discord_guild_id → server_db_id (FK dans persistent_messages).
    """
    try:
        server_db_id = await get_or_create_server_record(discord_guild_id, guild_name)
        if not server_db_id:
            return None

        query = """
            SELECT channel_id, message_id 
              FROM persistent_messages 
             WHERE guild_id = $1
               AND message_type = $2
        """
        record = await database.fetchrow(query, server_db_id, message_type)
        if record:
            logger.debug(
                f"Message persistant récupéré: server_db_id={server_db_id}, "
                f"type={message_type}, channel_id={record['channel_id']}, message_id={record['message_id']}"
            )
            return {'channel_id': record['channel_id'], 'message_id': record['message_id']}
        else:
            logger.warning(
                f"Aucun message persistant trouvé pour server_db_id={server_db_id}, type={message_type}."
            )
            return None
    except Exception as e:
        logger.error(f"Erreur lors de la récupération du message persistant: {e}")
        return None

async def delete_persistent_message(discord_guild_id: int, message_type: str, guild_name: str = "Inconnu") -> bool:
    """
    Supprime l'enregistrement d'un message persistant pour un type donné.
    """
    try:
        server_db_id = await get_or_create_server_record(discord_guild_id, guild_name)
        if not server_db_id:
            return False

        query = """
            DELETE FROM persistent_messages 
             WHERE guild_id = $1
               AND message_type = $2;
        """
        await database.execute(query, server_db_id, message_type)
        logger.info(f"Message persistant supprimé: server_db_id={server_db_id}, type={message_type}")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de la suppression du message persistant: {e}")
        return False


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
        INSERT INTO valorant_info (user_id, pseudo, tag)
        VALUES ($1, $2, $3)
        ON CONFLICT (user_id)
        DO UPDATE SET pseudo = EXCLUDED.pseudo,
                      tag    = EXCLUDED.tag;
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
# Supprimer données Valorant
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

        # Construit le dict { "fer": 123456789, "bronze": 987654321, ... }
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
    # Pour forcer la recréation du cache :
    await get_role_mappings(guild_id, guild_name)

async def get_users_with_update_flag_false() -> list:
    """
    Récupère tous les utilisateurs (jointure valorant_info + user_id)
    où needs_update = FALSE.
    """
    query = """
        SELECT u.discord_id,
               v.pseudo  AS valorant_pseudo,
               v.tag     AS valorant_tag,
               v.puuid   AS valorant_puuid,
               v.region  AS valorant_region,
               v.rank    AS valorant_rank,
               v.elo     AS valorant_elo
          FROM valorant_info v
          JOIN user_id u ON u.id = v.user_id
         WHERE v.needs_update = FALSE
           AND v.pseudo IS NOT NULL
           AND v.tag    IS NOT NULL
    """
    try:
        return await database.fetch(query)
    except Exception as e:
        logger.error(f"[get_users_with_update_flag_false] Erreur: {e}")
        return []


async def mark_user_update_flag_true(discord_id: int) -> None:
    """
    Met needs_update = TRUE pour l'utilisateur donné (via discord_id).
    """
    query = """
        UPDATE valorant_info v
           SET needs_update = TRUE
          FROM user_id u
         WHERE u.id = v.user_id
           AND u.discord_id = $1
    """
    try:
        await database.execute(query, discord_id)
        logger.debug(f"[mark_user_update_flag_true] Discord ID {discord_id} -> needs_update=TRUE.")
    except Exception as e:
        logger.error(f"[mark_user_update_flag_true] Erreur: {e}")


async def reset_all_update_flag_false() -> None:
    """
    Remet tous les utilisateurs à needs_update = FALSE.
    """
    query = "UPDATE valorant_info SET needs_update = FALSE"
    try:
        await database.execute(query)
        logger.info("[reset_all_update_flag_false] Tout le monde repasse à needs_update=FALSE.")
    except Exception as e:
        logger.error(f"[reset_all_update_flag_false] Erreur: {e}")