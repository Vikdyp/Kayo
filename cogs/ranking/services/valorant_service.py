import aiohttp
import logging
import os
from typing import Dict, List, Optional, Tuple
from aiolimiter import AsyncLimiter
from dotenv import load_dotenv

# Charger les variables d'environnement depuis le fichier .env
load_dotenv()

logger = logging.getLogger("valorant_service")

API_KEY = os.getenv("HENRIK_VALO_KEY")
HEADERS = {"Authorization": API_KEY} if API_KEY else {}

BASE_URL = "https://api.henrikdev.xyz/valorant/v2"

# Limiteur de taux : 90 requêtes par minute
rate_limiter = AsyncLimiter(max_rate=90, time_period=60)

# Exception personnalisée pour indiquer un dépassement de quota (429)
class RateLimitException(Exception):
    pass

_session: Optional[aiohttp.ClientSession] = None

def get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        timeout = aiohttp.ClientTimeout(total=10)
        _session = aiohttp.ClientSession(timeout=timeout)
    return _session

async def close_session():
    global _session
    if _session and not _session.closed:
        await _session.close()
        _session = None

async def get_puuid(player_name: str, player_tag: str) -> Optional[Tuple[str, str, str]]:
    """
    Récupère le PUUID, la région et le nom complet (nom#tag) d'un joueur.
    Lève RateLimitException si code 429.
    """
    url = f"{BASE_URL}/account/{player_name}/{player_tag}"
    logger.info(f"Envoi de la requête à l'URL: {url}")

    async with rate_limiter:
        session = get_session()
        try:
            async with session.get(url, headers=HEADERS) as response:
                if response.status == 200:
                    data = await response.json()
                    nom = data["data"]["name"]
                    tag = data["data"]["tag"]
                    region = data["data"]["region"]
                    puuid = data["data"]["puuid"]
                    nom_tag = f"{nom}#{tag}"
                    logger.info(f"PUUID récupéré pour {nom_tag}: {puuid}, Région: {region}")
                    return nom_tag, region, puuid

                elif response.status == 404:
                    logger.warning(f"Aucun compte trouvé pour {player_name}#{player_tag}.")
                    return None

                elif response.status == 429:
                    data = await response.json()
                    error_message = data.get("message", "Erreur inconnue.")
                    logger.error(f"Erreur 429 lors de la récupération du PUUID: {error_message}")
                    # On lève l'exception RateLimitException
                    raise RateLimitException(error_message)

                else:
                    data = await response.json()
                    error_message = data.get("message", "Erreur inconnue.")
                    logger.error(f"Erreur {response.status} lors de la récupération du PUUID: {error_message}")
                    return None

        except RateLimitException:
            # On la relance pour qu'elle remonte jusqu'à la tâche de mise à jour
            raise
        except Exception as e:
            logger.error(f"Exception lors de la récupération du PUUID pour {player_name}#{player_tag}: {e}")
            return None

async def get_player_rank(region: str, puuid: str) -> Optional[Tuple[str, int]]:
    """
    Récupère le rang et l'Elo d'un joueur à partir de son PUUID et de sa région.
    Lève RateLimitException si code 429.
    """
    url = f"{BASE_URL}/by-puuid/mmr/{region}/{puuid}"
    logger.info(f"Envoi de la requête de rang à l'URL: {url}")

    async with rate_limiter:
        session = get_session()
        try:
            async with session.get(url, headers=HEADERS) as response:
                if response.status == 200:
                    data = await response.json()
                    current_data = data["data"]["current_data"]
                    rank = current_data["currenttierpatched"]
                    elo = current_data["elo"]
                    logger.info(f"Statistiques récupérées pour PUUID {puuid}: Rang={rank}, Elo={elo}")
                    return rank, elo

                elif response.status == 429:
                    data = await response.json()
                    error_message = data.get("message", "Erreur inconnue.")
                    logger.error(f"Erreur 429 lors de la récupération des statistiques: {error_message}")
                    # On lève l'exception RateLimitException
                    raise RateLimitException(error_message)

                elif response.status == 404:
                    logger.warning(f"Aucun rang trouvé pour PUUID {puuid}.")
                    return None

                else:
                    data = await response.json()
                    error_message = data.get("message", "Erreur inconnue.")
                    logger.error(
                        f"Erreur {response.status} lors de la récupération des "
                        f"statistiques: {error_message}"
                    )
                    return None

        except RateLimitException:
            # On la relance pour qu'elle remonte jusqu'à la tâche de mise à jour
            raise
        except Exception as e:
            logger.error(f"Exception lors de la récupération des statistiques pour PUUID {puuid}: {e}")
            return None

async def get_mmr_history(
    region: str,
    puuid: str,
    platform: str = "pc"
) -> List[dict]:
    """
    Récupère l'historique complet de MMR pour un joueur donné.
    Utilise le endpoint v2 avec le paramètre platform.
    Lève RateLimitException si code 429.
    """
    url = f"{BASE_URL}/by-puuid/mmr-history/{region}/{platform}/{puuid}"
    logger.info(f"[get_mmr_history] Début pour region={region}, platform={platform}, puuid={puuid}")
    logger.debug(f"[get_mmr_history] URL → {url}")

    async with rate_limiter:
        session = get_session()
        try:
            async with session.get(url, headers=HEADERS) as response:
                status = response.status
                data = await response.json()
                logger.info(f"[get_mmr_history] HTTP {status}")
                logger.debug(f"[get_mmr_history] Payload: {data!r}")

                if status == 200:
                    history = data["data"].get("history", [])
                    logger.info(f"[get_mmr_history] {len(history)} entrées reçues")
                    return history

                elif status == 404:
                    logger.warning(f"[get_mmr_history] Aucun historique pour {puuid}")
                    return []

                elif status == 429:
                    err = data.get("message", "")
                    logger.error(f"[get_mmr_history] 429 Rate Limit – {err}")
                    raise RateLimitException(err)

                else:
                    err = data.get("message", "Erreur inconnue")
                    logger.error(f"[get_mmr_history] {status} – {err}")
                    return []

        except RateLimitException:
            raise
        except Exception as e:
            logger.exception(f"[get_mmr_history] Exception pour {puuid}")
            return []

async def get_stored_mmr_history(
    region: str,
    puuid: str,
    platform: str = "pc",
    page: int = 1,
    size: int = 100
) -> List[Dict]:
    """
    Récupère l'intégralité de l'historique de MMR via
    /v2/by-puuid/stored-mmr-history/{region}/{platform}/{puuid},
    en paginant jusqu'à épuisement.
    """
    history: List[Dict] = []
    while True:
        url = (
            f"{BASE_URL}/by-puuid/stored-mmr-history/"
            f"{region}/{platform}/{puuid}"
        )
        logger.info(f"[get_stored_mmr_history] page={page}, size={size}")
        async with rate_limiter:
            session = get_session()
            async with session.get(url, params={"page": page, "size": size}, headers=HEADERS) as resp:
                logger.info(f"[get_stored_mmr_history] HTTP {resp.status}")
                if resp.status == 200:
                    data = await resp.json()
                    batch = data.get("data", [])
                    logger.info(f"[get_stored_mmr_history] reçu {len(batch)} entrées")
                    history.extend(batch)
                    # si on a reçu moins que la page, on a tout
                    if len(batch) < size:
                        break
                    page += 1
                elif resp.status == 404:
                    logger.warning(f"[get_stored_mmr_history] 404 – pas d'historique stocké pour {puuid}")
                    break
                elif resp.status == 429:
                    msg = (await resp.json()).get("message","")
                    logger.error(f"[get_stored_mmr_history] 429 RateLimit – {msg}")
                    raise RateLimitException(msg)
                else:
                    msg = (await resp.json()).get("message","Erreur")
                    logger.error(f"[get_stored_mmr_history] {resp.status} – {msg}")
                    break
    return history

async def get_featured_store() -> Optional[List[Dict]]:
    """Récupère les offres de la boutique en vedette."""
    url = f"{BASE_URL}/store-featured"
    async with rate_limiter:
        session = get_session()
        async with session.get(url, headers=HEADERS) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("data", [])
            elif resp.status == 429:
                msg = (await resp.json()).get("message", "")
                logger.error(f"[get_featured_store] 429 RateLimit – {msg}")
                raise RateLimitException(msg)
            else:
                msg = (await resp.json()).get("message", "Erreur")
                logger.error(f"[get_featured_store] {resp.status} – {msg}")
                return None

