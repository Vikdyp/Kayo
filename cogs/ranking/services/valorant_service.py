# cogs/ranking/services/valorant_service.py
import aiohttp
import logging
import os
from typing import Optional, Tuple
from aiolimiter import AsyncLimiter

from dotenv import load_dotenv

# Charger les variables d'environnement depuis le fichier .env
load_dotenv()

logger = logging.getLogger("valorant_service")

API_KEY = os.getenv("HENRIK_VALO_KEY")
HEADERS = {
    "Authorization": API_KEY
} if API_KEY else {}

BASE_URL = "https://api.henrikdev.xyz/valorant/v2"

# Limiteur de taux : 30 requêtes par minute
rate_limiter = AsyncLimiter(max_rate=30, time_period=60)

async def get_puuid(player_name: str, player_tag: str) -> Optional[Tuple[str, str, str]]:
    """
    Récupère le PUUID, la région et le nom complet (nom#tag) d'un joueur.

    Args:
        player_name (str): Le nom de l'utilisateur.
        player_tag (str): Le tag de l'utilisateur.

    Returns:
        Optional[Tuple[str, str, str]]: (nom_tag, region, puuid) si trouvé, sinon None.
    """
    url = f"{BASE_URL}/account/{player_name}/{player_tag}"
    logger.info(f"Envoi de la requête à l'URL: {url}")

    async with rate_limiter:
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=HEADERS) as response:
                    if response.status == 200:
                        data = await response.json()
                        nom = data['data']['name']
                        tag = data['data']['tag']
                        region = data['data']['region']
                        puuid = data['data']['puuid']
                        nom_tag = f"{nom}#{tag}"
                        logger.info(f"PUUID récupéré pour {nom_tag}: {puuid}, Région: {region}")
                        return nom_tag, region, puuid
                    elif response.status == 404:
                        logger.warning(f"Aucun compte trouvé pour {player_name}#{player_tag}.")
                        return None
                    else:
                        data = await response.json()
                        error_message = data.get('message', 'Erreur inconnue.')
                        logger.error(f"Erreur {response.status} lors de la récupération du PUUID: {error_message}")
                        return None
            except Exception as e:
                logger.error(f"Exception lors de la récupération du PUUID pour {player_name}#{player_tag}: {e}")
                return None

async def get_player_rank(region: str, puuid: str) -> Optional[Tuple[str, int]]:
    """
    Récupère le rang et l'Elo d'un joueur à partir de son PUUID et de sa région.

    Args:
        region (str): La région du joueur (ex: 'eu').
        puuid (str): Le PUUID du joueur.

    Returns:
        Optional[Tuple[str, int]]: (rank, elo) si trouvé, sinon None.
    """
    url = f"{BASE_URL}/by-puuid/mmr/{region}/{puuid}"
    logger.info(f"Envoi de la requête de rang à l'URL: {url}")

    async with rate_limiter:
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=HEADERS) as response:
                    if response.status == 200:
                        data = await response.json()
                        current_data = data['data']['current_data']
                        rank = current_data['currenttierpatched']
                        elo = current_data['elo']
                        logger.info(f"Statistiques récupérées pour PUUID {puuid}: Rang={rank}, Elo={elo}")
                        return rank, elo
                    elif response.status == 404:
                        logger.warning(f"Aucun rang trouvé pour PUUID {puuid}.")
                        return None
                    else:
                        data = await response.json()
                        error_message = data.get('message', 'Erreur inconnue.')
                        logger.error(f"Erreur {response.status} lors de la récupération des statistiques: {error_message}")
                        return None
            except Exception as e:
                logger.error(f"Exception lors de la récupération des statistiques pour PUUID {puuid}: {e}")
                return None
