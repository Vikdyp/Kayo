import asyncio
from typing import Optional, Dict
from utils.database import database
import logging

logger = logging.getLogger("rank_service")

# Les rangs Valorant de base
RANGS_VALORANT = (
    'fer', 'bronze', 'argent', 'or', 'platine',
    'diamant', 'ascendant', 'immortel', 'radiant', 'no_rank'
)

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
# USER VALORANT INFO
# ------------------------------------------------

async def update_user_valorant_info(discord_id: int, pseudo: str, tag: str) -> bool:
    query = """
        INSERT INTO user_id (discord_id, valorant_pseudo, valorant_tag)
        VALUES ($1, $2, $3)
        ON CONFLICT (discord_id)
        DO UPDATE SET valorant_pseudo = EXCLUDED.valorant_pseudo,
                      valorant_tag = EXCLUDED.valorant_tag;
    """
    try:
        await database.execute(query, discord_id, pseudo, tag)
        logger.info(f"Informations Valorant mises à jour pour Discord ID {discord_id}: {pseudo}#{tag}")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de la mise à jour des informations Valorant pour Discord ID {discord_id}: {e}")
        return False

async def set_valorant_details(discord_id: int, puuid: str, region: str, rank: str, elo: int) -> bool:
    query = """
        UPDATE user_id
        SET valorant_puuid = $1,
            valorant_region = $2,
            valorant_rank = $3,
            valorant_elo = $4
        WHERE discord_id = $5;
    """
    try:
        await database.execute(query, puuid, region, rank, elo, discord_id)
        logger.info(f"Détails Valorant mis à jour pour Discord ID {discord_id}: PUUID={puuid}, Région={region}, Rang={rank}, Elo={elo}")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de la mise à jour des détails Valorant pour Discord ID {discord_id}: {e}")
        return False

async def get_all_users_with_valo_info() -> list:
    query = """
        SELECT discord_id, valorant_pseudo, valorant_tag, valorant_puuid, valorant_region, valorant_rank, valorant_elo
        FROM user_id
        WHERE valorant_pseudo IS NOT NULL AND valorant_tag IS NOT NULL;
    """
    try:
        records = await database.fetch(query)
        logger.info(f"{len(records)} utilisateurs récupérés pour la mise à jour Valorant.")
        return records
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des utilisateurs pour la mise à jour Valorant: {e}")
        return []

# ------------------------------------------------
# RÔLES : gestion + cache local
# ------------------------------------------------
_role_cache: Dict[int, Dict[str, int]] = {}
_role_cache_lock = asyncio.Lock()

async def get_role_id_for_config(guild_id: int, guild_name: str, role_config_pk: int) -> Optional[int]:
    """
    Récupère le 'role_id' (ID Discord du rôle) dans la table roles_configurations,
    en se basant sur la PK `id` de roles_configurations ( = role_config_pk ).
    On utilise server_id comme FK.
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

# ------------------------------------------------
# Supprimer données Valorant
# ------------------------------------------------
async def delete_valo_data(discord_id: int) -> bool:
    query = """
        UPDATE user_id
           SET valorant_pseudo = NULL,
               valorant_tag = NULL,
               valorant_puuid = NULL,
               valorant_region = NULL,
               valorant_rank = NULL,
               valorant_elo = NULL
         WHERE discord_id = $1
    """
    try:
        await database.execute(query, discord_id)
        logger.info(f"Données Valorant supprimées pour Discord ID {discord_id}.")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de la suppression des données Valorant pour {discord_id}: {e}")
        return False

async def user_exists_in_db(discord_id: int) -> bool:
    query = """
        SELECT 1
          FROM user_id
         WHERE discord_id = $1
         LIMIT 1
    """
    record = await database.fetchrow(query, discord_id)
    return record is not None
