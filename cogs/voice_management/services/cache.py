# cogs/voice_management/services/cache.py
"""
Cache centralisé avec TTL pour le système de matchmaking.
Utilise une implémentation simple sans dépendance externe.
"""

import asyncio
import logging
import time
from typing import Dict, Optional, Any, TypeVar, Generic, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class CacheEntry(Generic[T]):
    """Entrée de cache avec expiration."""
    value: T
    expires_at: float
    created_at: float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        return time.time() > self.expires_at


class TTLCache(Generic[T]):
    """
    Cache simple avec TTL (Time To Live).

    Implémentation thread-safe utilisant asyncio.Lock pour les opérations async.
    """

    def __init__(self, maxsize: int = 100, ttl: float = 300):
        """
        Args:
            maxsize: Nombre maximum d'entrées dans le cache
            ttl: Durée de vie en secondes (par défaut: 5 minutes)
        """
        self._cache: Dict[Any, CacheEntry[T]] = {}
        self._maxsize = maxsize
        self._ttl = ttl
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0

    async def get(self, key: Any) -> Optional[T]:
        """
        Récupère une valeur du cache.

        Args:
            key: Clé de l'entrée

        Returns:
            Valeur si trouvée et non expirée, None sinon
        """
        async with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._misses += 1
                return None

            if entry.is_expired():
                del self._cache[key]
                self._misses += 1
                return None

            self._hits += 1
            return entry.value

    async def set(self, key: Any, value: T, ttl: Optional[float] = None) -> None:
        """
        Stocke une valeur dans le cache.

        Args:
            key: Clé de l'entrée
            value: Valeur à stocker
            ttl: TTL personnalisé (utilise le défaut si None)
        """
        async with self._lock:
            # Si le cache est plein, supprimer les entrées expirées d'abord
            if len(self._cache) >= self._maxsize:
                await self._cleanup_expired_unsafe()

            # Si toujours plein, supprimer l'entrée la plus ancienne
            if len(self._cache) >= self._maxsize:
                oldest_key = min(
                    self._cache.keys(),
                    key=lambda k: self._cache[k].created_at
                )
                del self._cache[oldest_key]

            expires_at = time.time() + (ttl if ttl is not None else self._ttl)
            self._cache[key] = CacheEntry(value=value, expires_at=expires_at)

    async def delete(self, key: Any) -> bool:
        """
        Supprime une entrée du cache.

        Returns:
            True si l'entrée existait, False sinon
        """
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    async def clear(self) -> None:
        """Vide le cache."""
        async with self._lock:
            self._cache.clear()

    async def cleanup_expired(self) -> int:
        """
        Supprime les entrées expirées.

        Returns:
            Nombre d'entrées supprimées
        """
        async with self._lock:
            return await self._cleanup_expired_unsafe()

    async def _cleanup_expired_unsafe(self) -> int:
        """Version non-thread-safe de cleanup (appelée avec le lock déjà acquis)."""
        expired_keys = [
            key for key, entry in self._cache.items()
            if entry.is_expired()
        ]
        for key in expired_keys:
            del self._cache[key]
        return len(expired_keys)

    def __contains__(self, key: Any) -> bool:
        """Vérifie si une clé existe (synchrone, sans vérification d'expiration)."""
        return key in self._cache

    def __len__(self) -> int:
        """Retourne le nombre d'entrées (incluant potentiellement les expirées)."""
        return len(self._cache)

    @property
    def stats(self) -> Dict[str, int]:
        """Retourne les statistiques du cache."""
        return {
            'size': len(self._cache),
            'maxsize': self._maxsize,
            'hits': self._hits,
            'misses': self._misses,
            'hit_rate': self._hits / (self._hits + self._misses) if (self._hits + self._misses) > 0 else 0
        }


class MatchmakingCache:
    """
    Cache centralisé pour toutes les opérations de matchmaking.

    Caches disponibles:
    - server_id: guild_id -> server_id (TTL: 1h)
    - user_info: discord_id -> user_info dict (TTL: 5min)
    - queue_counts: server_id -> counts dict (TTL: 15s)
    - team_info: (code, server_id) -> team dict (TTL: 2min)
    """

    def __init__(self):
        # Cache pour les server_id (rarement change)
        self._server_id_cache: TTLCache[int] = TTLCache(maxsize=100, ttl=3600)  # 1h

        # Cache pour les infos utilisateur (change avec ELO updates)
        self._user_info_cache: TTLCache[Dict] = TTLCache(maxsize=1000, ttl=300)  # 5min

        # Cache pour les comptages de queue (change fréquemment)
        self._queue_counts_cache: TTLCache[Dict] = TTLCache(maxsize=100, ttl=15)  # 15s

        # Cache pour les infos d'équipe
        self._team_info_cache: TTLCache[Dict] = TTLCache(maxsize=500, ttl=120)  # 2min

    # --- Server ID Cache ---

    async def get_server_id(self, guild_id: int) -> Optional[int]:
        """Récupère le server_id depuis le cache."""
        return await self._server_id_cache.get(guild_id)

    async def set_server_id(self, guild_id: int, server_id: int) -> None:
        """Stocke le server_id dans le cache."""
        await self._server_id_cache.set(guild_id, server_id)

    # --- User Info Cache ---

    async def get_user_info(self, discord_id: int) -> Optional[Dict]:
        """Récupère les infos utilisateur depuis le cache."""
        return await self._user_info_cache.get(discord_id)

    async def set_user_info(self, discord_id: int, info: Dict) -> None:
        """Stocke les infos utilisateur dans le cache."""
        await self._user_info_cache.set(discord_id, info)

    async def invalidate_user(self, discord_id: int) -> None:
        """Invalide le cache d'un utilisateur (après mise à jour ELO)."""
        await self._user_info_cache.delete(discord_id)

    # --- Queue Counts Cache ---

    async def get_queue_counts(self, server_id: int) -> Optional[Dict]:
        """Récupère les comptages de queue depuis le cache."""
        return await self._queue_counts_cache.get(server_id)

    async def set_queue_counts(self, server_id: int, counts: Dict) -> None:
        """Stocke les comptages de queue dans le cache."""
        await self._queue_counts_cache.set(server_id, counts)

    async def invalidate_queue_counts(self, server_id: int) -> None:
        """Invalide le cache des comptages (après ajout/suppression en queue)."""
        await self._queue_counts_cache.delete(server_id)

    # --- Team Info Cache ---

    async def get_team_info(self, code: str, server_id: int) -> Optional[Dict]:
        """Récupère les infos d'équipe depuis le cache."""
        return await self._team_info_cache.get((code, server_id))

    async def set_team_info(self, code: str, server_id: int, info: Dict) -> None:
        """Stocke les infos d'équipe dans le cache."""
        await self._team_info_cache.set((code, server_id), info)

    async def invalidate_team(self, code: str, server_id: int) -> None:
        """Invalide le cache d'une équipe."""
        await self._team_info_cache.delete((code, server_id))

    # --- Cleanup ---

    async def cleanup_all(self) -> Dict[str, int]:
        """
        Nettoie les entrées expirées de tous les caches.

        Returns:
            Dict avec le nombre d'entrées supprimées par cache
        """
        return {
            'server_id': await self._server_id_cache.cleanup_expired(),
            'user_info': await self._user_info_cache.cleanup_expired(),
            'queue_counts': await self._queue_counts_cache.cleanup_expired(),
            'team_info': await self._team_info_cache.cleanup_expired(),
        }

    @property
    def stats(self) -> Dict[str, Dict]:
        """Retourne les statistiques de tous les caches."""
        return {
            'server_id': self._server_id_cache.stats,
            'user_info': self._user_info_cache.stats,
            'queue_counts': self._queue_counts_cache.stats,
            'team_info': self._team_info_cache.stats,
        }


# Instance globale du cache
matchmaking_cache = MatchmakingCache()
