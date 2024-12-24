#cogs\accueil\services\accueil_services.py
from typing import Dict, Optional
from utils.database import database

async def get_welcome_channel_id(guild_id: int) -> Optional[int]:
    """
    Récupère l'ID du salon d'accueil pour une guilde donnée à partir de la table channel_configurations.
    
    :param guild_id: L'ID de la guilde Discord.
    :return: L'ID du salon d'accueil ou None si non trouvé.
    """
    query = """
        SELECT channel_id 
        FROM channel_configurations 
        WHERE guild_id = $1 AND action = 'welcome';
    """
    channel_id = await database.fetchval(query, guild_id)
    return channel_id

async def get_channel_ids(guild_id: int, actions: list) -> Dict[str, int]:
    """
    Récupère les IDs des salons pour les actions spécifiées.
    
    :param guild_id: L'ID de la guilde Discord.
    :param actions: Liste des actions pour lesquelles récupérer les salons.
    :return: Dictionnaire avec les actions comme clés et les IDs des salons comme valeurs.
    """
    query = """
        SELECT action, channel_id 
        FROM channel_configurations 
        WHERE guild_id = $1 AND action = ANY($2::text[]);
    """
    records = await database.fetch(query, guild_id, actions)
    return {record['action']: record['channel_id'] for record in records}
