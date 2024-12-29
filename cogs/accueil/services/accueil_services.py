#cogs\accueil\services\accueil_services.py
from typing import Dict, Optional
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
    
    :param guild_id: L'ID de la guilde Discord.
    :return: L'ID interne du serveur ou None si non trouvé.
    """
    query = """
        SELECT id 
        FROM serveur_id 
        WHERE guild_id = $1;
    """
    server_id = await database.fetchval(query, guild_id)
    return server_id
