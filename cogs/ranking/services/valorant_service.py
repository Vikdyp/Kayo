import aiohttp
import asyncio
import logging
import os
from functools import wraps
from typing import Callable, Dict, List, Optional, Tuple, TypeVar
from aiolimiter import AsyncLimiter
from dotenv import load_dotenv

# Charger les variables d'environnement depuis le fichier .env
load_dotenv()

logger = logging.getLogger("valorant_service")

API_KEY = os.getenv("HENRIK_VALO_KEY")
HEADERS = {"Authorization": API_KEY} if API_KEY else {}

BASE_URL = "https://api.henrikdev.xyz/valorant/v2"
VALORANT_API_URL = "https://valorant-api.com/v1"

# Limiteur de taux : 90 requêtes par minute
rate_limiter = AsyncLimiter(max_rate=90, time_period=60)

# Exception personnalisée pour indiquer un dépassement de quota (429)
class RateLimitException(Exception):
    pass


# Type variable pour le décorateur
T = TypeVar('T')


def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    exponential: bool = True
) -> Callable:
    """
    Décorateur ajoutant une logique de retry avec backoff exponentiel.
    Ne réessaye PAS sur RateLimitException (429) - celles-ci doivent remonter.

    Args:
        max_retries: Nombre maximum de tentatives
        base_delay: Délai de base entre les tentatives (en secondes)
        exponential: Si True, utilise un backoff exponentiel
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except RateLimitException:
                    # Ne pas réessayer les rate limits - les laisser remonter
                    raise
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt) if exponential else base_delay
                        logger.warning(
                            f"[{func.__name__}] Tentative {attempt + 1}/{max_retries} échouée: {e}. "
                            f"Nouvelle tentative dans {delay:.1f}s..."
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"[{func.__name__}] Toutes les {max_retries} tentatives ont échoué.")
            return None
        return wrapper
    return decorator

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

@with_retry(max_retries=3, base_delay=1.0)
async def get_puuid(player_name: str, player_tag: str) -> Optional[Tuple[str, str, str]]:
    """
    Récupère le PUUID, la région et le nom complet (nom#tag) d'un joueur.
    Lève RateLimitException si code 429.
    Réessaye automatiquement en cas d'erreur réseau (max 3 tentatives).
    """
    url = f"{BASE_URL}/account/{player_name}/{player_tag}"
    logger.info(f"Envoi de la requête à l'URL: {url}")

    async with rate_limiter:
        session = get_session()
        try:
            async with session.get(url, headers=HEADERS) as response:
                if response.status == 200:
                    data = await response.json()
                    player_data = data.get("data")
                    if not player_data:
                        logger.error(f"[get_puuid] Champ 'data' manquant pour {player_name}#{player_tag}")
                        return None
                    nom = player_data.get("name")
                    tag = player_data.get("tag")
                    region = player_data.get("region")
                    puuid = player_data.get("puuid")
                    if not all([nom, tag, region, puuid]):
                        logger.error(f"[get_puuid] Données incomplètes pour {player_name}#{player_tag}: {player_data}")
                        return None
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

@with_retry(max_retries=3, base_delay=1.0)
async def get_player_rank(region: str, puuid: str) -> Optional[Tuple[str, int]]:
    """
    Récupère le rang et l'Elo d'un joueur à partir de son PUUID et de sa région.
    Lève RateLimitException si code 429.
    Réessaye automatiquement en cas d'erreur réseau (max 3 tentatives).
    """
    url = f"{BASE_URL}/by-puuid/mmr/{region}/{puuid}"
    logger.info(f"Envoi de la requête de rang à l'URL: {url}")

    async with rate_limiter:
        session = get_session()
        try:
            async with session.get(url, headers=HEADERS) as response:
                if response.status == 200:
                    data = await response.json()
                    player_data = data.get("data")
                    if not player_data:
                        logger.error(f"[get_player_rank] Champ 'data' manquant pour PUUID {puuid}")
                        return None
                    current_data = player_data.get("current_data")
                    if not current_data:
                        logger.warning(f"[get_player_rank] Pas de current_data pour PUUID {puuid} - peut-être non classé")
                        return None
                    rank = current_data.get("currenttierpatched")
                    elo = current_data.get("elo")
                    if rank is None or elo is None:
                        logger.warning(f"[get_player_rank] Rang ou elo manquant pour PUUID {puuid}")
                        return None
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

@with_retry(max_retries=3, base_delay=1.0)
async def get_mmr_history(
    region: str,
    puuid: str,
    platform: str = "pc"
) -> List[dict]:
    """
    Récupère l'historique complet de MMR pour un joueur donné.
    Utilise le endpoint v2 avec le paramètre platform.
    Lève RateLimitException si code 429.
    Réessaye automatiquement en cas d'erreur réseau (max 3 tentatives).
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

async def get_bundle_info(bundle_uuid: str) -> Optional[Dict]:
    """Récupère les informations détaillées d'un bundle."""
    url = f"{VALORANT_API_URL}/bundles/{bundle_uuid}"
    async with rate_limiter:
        session = get_session()
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("data")
            elif resp.status == 429:
                msg = (await resp.json()).get("message", "")
                logger.error(f"[get_bundle_info] 429 RateLimit – {msg}")
                raise RateLimitException(msg)
            else:
                msg = (await resp.json()).get("message", "Erreur")
                logger.error(f"[get_bundle_info] {resp.status} – {msg}")
                return None

