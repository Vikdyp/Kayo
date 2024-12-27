# cogs\ranking\services\assign_rank_service.py
import asyncio
from typing import Optional, Dict
from utils.database import database
import logging

logger = logging.getLogger("embed_service")

# On définit les rangs Valorant de base :
RANGS_VALORANT = (
    'fer', 'bronze', 'argent', 'or', 'platine',
    'diamant', 'ascendant', 'immortel', 'radiant', 'no_rank'
)

# --- Gestion des Messages Persistants ---

async def store_persistent_message(guild_id: int, channel_id: int, message_id: int, message_type: str) -> bool:
    """
    Stocke ou met à jour les informations d'un message persistant dans la base de données.

    :param guild_id: ID de la guilde Discord.
    :param channel_id: ID du salon Discord.
    :param message_id: ID du message Discord.
    :param message_type: Type du message (e.g., 'embed_selection').
    :return: True si réussi, False sinon.
    """
    query = """
        INSERT INTO persistent_messages (guild_id, channel_id, message_id, message_type)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (guild_id, message_type) DO UPDATE
        SET channel_id = EXCLUDED.channel_id,
            message_id = EXCLUDED.message_id,
            created_at = now();
    """
    try:
        await database.execute(query, guild_id, channel_id, message_id, message_type)
        logger.info(f"Message persistant stocké: guild_id={guild_id}, channel_id={channel_id}, message_id={message_id}, type={message_type}")
        return True
    except Exception as e:
        logger.error(f"Erreur lors du stockage du message persistant: {e}")
        return False

async def get_persistent_message(guild_id: int, message_type: str) -> Optional[Dict[str, int]]:
    """
    Récupère les informations d'un message persistant spécifique.

    :param guild_id: ID de la guilde Discord.
    :param message_type: Type du message.
    :return: Dictionnaire avec 'channel_id' et 'message_id' ou None si non trouvé.
    """
    query = """
        SELECT channel_id, message_id 
        FROM persistent_messages 
        WHERE guild_id = $1 AND message_type = $2;
    """
    record = await database.fetchrow(query, guild_id, message_type)
    if record:
        logger.debug(f"Message persistant récupéré: guild_id={guild_id}, type={message_type}, channel_id={record['channel_id']}, message_id={record['message_id']}")
        return {'channel_id': record['channel_id'], 'message_id': record['message_id']}
    else:
        logger.warning(f"Aucun message persistant trouvé pour guild_id={guild_id} et type={message_type}.")
        return None

async def delete_persistent_message(guild_id: int, message_type: str) -> bool:
    """
    Supprime les informations d'un message persistant de la base de données.

    :param guild_id: ID de la guilde Discord.
    :param message_type: Type du message.
    :return: True si réussi, False sinon.
    """
    query = """
        DELETE FROM persistent_messages 
        WHERE guild_id = $1 AND message_type = $2;
    """
    try:
        await database.execute(query, guild_id, message_type)
        logger.info(f"Message persistant supprimé: guild_id={guild_id}, type={message_type}")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de la suppression du message persistant: {e}")
        return False

# --- Gestion des Configurations de Salon ---

async def get_channel_id(guild_id: int, action: str) -> Optional[int]:
    """
    Récupère l'ID du salon pour une action spécifique dans une guilde donnée.

    :param guild_id: ID de la guilde Discord.
    :param action: Action spécifique (e.g., 'rang').
    :return: ID du salon ou None si non trouvé.
    """
    query = """
        SELECT channel_id
        FROM channel_configurations
        WHERE guild_id = $1 AND action = $2;
    """
    channel_id = await database.fetchval(query, guild_id, action)
    if channel_id:
        logger.debug(f"Salon trouvé: guild_id={guild_id}, action={action}, channel_id={channel_id}")
    else:
        logger.warning(f"Aucun salon trouvé pour guild_id={guild_id} et action='{action}'.")
    return channel_id

async def set_channel_id(guild_id: int, action: str, channel_id: int) -> bool:
    """
    Définit ou met à jour l'ID du salon pour une action spécifique dans une guilde donnée.

    :param guild_id: ID de la guilde Discord.
    :param action: Action spécifique (e.g., 'rang').
    :param channel_id: ID du salon Discord.
    :return: True si réussi, False sinon.
    """
    query = """
        INSERT INTO channel_configurations (guild_id, action, channel_id)
        VALUES ($1, $2, $3)
        ON CONFLICT (guild_id, action) DO UPDATE
        SET channel_id = EXCLUDED.channel_id;
    """
    try:
        await database.execute(query, guild_id, action, channel_id)
        logger.info(f"Salon défini: guild_id={guild_id}, action='{action}', channel_id={channel_id}")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de la définition du salon pour guild_id={guild_id}, action='{action}': {e}")
        return False

# --- Gestion des Informations Valorant des Utilisateurs ---

async def update_user_valorant_info(discord_id: int, pseudo: str, tag: str) -> bool:
    """
    Met à jour ou insère les informations Valorant d'un utilisateur dans la base de données.

    :param discord_id: ID Discord de l'utilisateur.
    :param pseudo: Pseudo Valorant de l'utilisateur.
    :param tag: Tag Valorant de l'utilisateur.
    :return: True si réussi, False sinon.
    """
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
    """
    Met à jour les détails Valorant (puuid, region, rank, elo) d'un utilisateur dans la base de données.

    :param discord_id: ID Discord de l'utilisateur.
    :param puuid: PUUID du joueur.
    :param region: Région du joueur.
    :param rank: Rang Valorant du joueur.
    :param elo: Elo du joueur.
    :return: True si réussi, False sinon.
    """
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
    """
    Récupère tous les utilisateurs avec un pseudo et un tag Valorant enregistrés.

    :return: Liste de dictionnaires contenant les informations des utilisateurs.
    """
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

# --- Gestion des Configurations de Rôles ---
# Ajoutons un cache simple pour stocker les mappings de rôles par guilde
_role_cache: Dict[int, Dict[str, int]] = {}
_role_cache_lock = asyncio.Lock()  # Pour assurer la sécurité des accès concurrents au cache

async def get_role_mappings(guild_id: int) -> Optional[Dict[str, int]]:
    """
    Récupère les mappings des rôles de rang Valorant pour une guilde spécifique depuis la base de données,
    en ne conservant que les rôles correspondant aux rangs définis dans RANGS_VALORANT.
    Utilise un cache pour minimiser les appels à la base de données.

    :param guild_id: ID de la guilde Discord.
    :return: Dictionnaire mappant les noms de rang Valorant (en minuscules)
             aux IDs de rôles Discord, ou None si non trouvé.
    """
    async with _role_cache_lock:
        if guild_id in _role_cache:
            logger.debug(f"Récupération des mappings de rôles pour guild_id={guild_id} depuis le cache.")
            return _role_cache[guild_id]

    # Créer la liste de placeholders sous forme 'fer','bronze','argent', ...
    placeholders = ', '.join(f"'{r}'" for r in RANGS_VALORANT)
    query = f"""
        SELECT role_name, role_id
          FROM roles_configurations
         WHERE guild_id = $1
           AND role_name IN ({placeholders});
    """

    try:
        # On suppose que vous avez un objet "database" avec une méthode async "fetch"
        records = await database.fetch(query, guild_id)
        if not records:
            logger.warning(f"Aucun rôle de rang Valorant trouvé pour guild_id={guild_id}.")
            return None

        # On construit le dictionnaire { "fer": <role_id>, "argent": <role_id>, ... }
        role_mappings = {r['role_name'].lower(): r['role_id'] for r in records}

        # Mettre à jour le cache
        async with _role_cache_lock:
            _role_cache[guild_id] = role_mappings
            logger.info(f"Mappings de rôles Valorant pour guild_id={guild_id} mis en cache.")

        return role_mappings

    except Exception as e:
        logger.error(f"Erreur lors de la récupération des configurations de rôles pour guild_id={guild_id}: {e}")
        return None

async def refresh_role_mappings(guild_id: int):
    """
    Rafraîchit les mappings de rôles pour une guilde spécifique en vidant le cache.

    :param guild_id: ID de la guilde Discord.
    """
    async with _role_cache_lock:
        if guild_id in _role_cache:
            del _role_cache[guild_id]
            logger.info(f"Cache des mappings de rôles vidé pour guild_id={guild_id}.")

async def delete_valo_data(discord_id: int) -> bool:
    """
    Supprime les données Valorant d'un utilisateur dans la table user_id,
    c'est-à-dire pseudo, tag, puuid, region, rank, elo.
    """
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
        result = await database.execute(query, discord_id)
        logger.info(f"Données Valorant supprimées pour Discord ID {discord_id}.")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de la suppression des données Valorant pour {discord_id}: {e}")
        return False

async def user_exists_in_db(discord_id: int) -> bool:
    """
    Vérifie si un enregistrement existe pour 'discord_id' dans la table user_id.
    """
    query = """
        SELECT 1
          FROM user_id
         WHERE discord_id = $1
         LIMIT 1
    """
    record = await database.fetchrow(query, discord_id)
    return record is not None