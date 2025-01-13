#cogs\accueil\services\accueil_services.py
from datetime import date, datetime
from typing import Dict, List, Optional
from utils.database import database

async def get_welcome_channel_id(guild_id: int) -> Optional[int]:
    server_id = await get_server_id(guild_id)
    if server_id is None:
        return None
    
    query = """
        SELECT channel_id 
        FROM channel_configurations 
        WHERE server_id = $1 AND action = 'welcome';
    """
    channel_id = await database.fetchval(query, server_id)
    return channel_id

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
    """
    Récupère l'ID interne du serveur à partir de l'ID de la guilde Discord.
    """
    query = """
        SELECT id 
        FROM serveur_id 
        WHERE guild_id = $1;
    """
    server_id = await database.fetchval(query, guild_id)
    return server_id

# =========================
# Fonctions pour le suivi des membres en BDD
# =========================

async def log_member_event_aggregated(guild_id: int, event_type: str) -> None:
    """
    Incrémente le compteur join/leave dans la table member_daily_stats.
    Maintenant, on utilise l'ID interne du serveur récupéré dans la table serveur_id.
    """
    # Récupérer l'ID interne du serveur à partir du guild_id Discord
    server_id = await get_server_id(guild_id)
    if server_id is None:
        # On peut choisir de ne rien faire ou de loguer une erreur si le mapping n'existe pas
        return

    # On prend la date du jour
    today = date.today()

    # Vérifie si la ligne (server_id, today) existe déjà dans member_daily_stats
    query_select = """
        SELECT join_count, leave_count
        FROM member_daily_stats
        WHERE guild_id = $1 AND date = $2
    """
    record = await database.fetchrow(query_select, server_id, today)

    if record is None:
        # Insérer une nouvelle ligne
        if event_type == "join":
            query_insert = """
                INSERT INTO member_daily_stats (guild_id, date, join_count, leave_count)
                VALUES ($1, $2, 1, 0);
            """
        else:  # leave
            query_insert = """
                INSERT INTO member_daily_stats (guild_id, date, join_count, leave_count)
                VALUES ($1, $2, 0, 1);
            """
        await database.execute(query_insert, server_id, today)
    else:
        # Mettre à jour la ligne existante
        if event_type == "join":
            new_join_count = record['join_count'] + 1
            query_update = """
                UPDATE member_daily_stats
                SET join_count = $3
                WHERE guild_id = $1 AND date = $2
            """
            await database.execute(query_update, server_id, today, new_join_count)
        else:  # leave
            new_leave_count = record['leave_count'] + 1
            query_update = """
                UPDATE member_daily_stats
                SET leave_count = $3
                WHERE guild_id = $1 AND date = $2
            """
            await database.execute(query_update, server_id, today, new_leave_count)

async def get_aggregated_stats(guild_id: int) -> dict:
    """
    Retourne un dictionnaire avec les stats sur 24h, 7j, 30j, et totaux.
    Les requêtes se font sur la table member_daily_stats en utilisant l'ID interne du serveur.
    """
    server_id = await get_server_id(guild_id)
    if server_id is None:
        # Retourner des valeurs par défaut ou lever une exception si le mapping n'existe pas
        return {
            "join_24h": 0, "leave_24h": 0,
            "join_7d": 0, "leave_7d": 0,
            "join_30d": 0, "leave_30d": 0,
            "total_join": 0, "total_left": 0,
            "join_leave_ratio": 0
        }

    # Requête pour 24h : date >= CURRENT_DATE - 1
    query_24h = """
        SELECT COALESCE(SUM(join_count), 0) AS join_24h,
               COALESCE(SUM(leave_count), 0) AS leave_24h
        FROM member_daily_stats
        WHERE guild_id = $1
          AND date >= (CURRENT_DATE - 1);
    """
    # Requête pour 7 jours : date >= CURRENT_DATE - 7
    query_7d = """
        SELECT COALESCE(SUM(join_count), 0) AS join_7d,
               COALESCE(SUM(leave_count), 0) AS leave_7d
        FROM member_daily_stats
        WHERE guild_id = $1
          AND date >= (CURRENT_DATE - 7);
    """
    # Requête pour 30 jours : date >= CURRENT_DATE - 30
    query_30d = """
        SELECT COALESCE(SUM(join_count), 0) AS join_30d,
               COALESCE(SUM(leave_count), 0) AS leave_30d
        FROM member_daily_stats
        WHERE guild_id = $1
          AND date >= (CURRENT_DATE - 30);
    """
    # Requête pour le total global
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

    # Calcul du ratio
    if total_left == 0:
        ratio = float(total_join)  # ou éventuellement définir un ratio spécifique
    else:
        ratio = round(total_join / total_left, 2)

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

async def get_member_evolution(guild_id: int) -> List[Dict]:
    """
    Récupère les données d'évolution des membres sur les 30 derniers jours.
    Les requêtes se font sur la table member_daily_stats en utilisant l'ID interne du serveur.
    Chaque élément est un dictionnaire contenant :
      - 'date': la date de la donnée
      - 'join_count': le nombre d'adhésions ce jour-là
      - 'leave_count': le nombre de départs ce jour-là
    """
    server_id = await get_server_id(guild_id)
    if server_id is None:
        return []

    query = """
        SELECT date, join_count, leave_count
        FROM member_daily_stats
        WHERE guild_id = $1
          AND date >= (CURRENT_DATE - 30)
        ORDER BY date ASC;
    """
    records = await database.fetch(query, server_id)
    # Assure-toi que les dates sont au format datetime.date
    return [dict(record) for record in records]
