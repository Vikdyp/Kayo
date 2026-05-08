# database/services/automod_config_service.py
"""
Gestion des transactions pour la configuration automod.
"""

from dataclasses import dataclass
from typing import Dict, Any, List, Optional

from database.repos.guilds_repo import GuildsRepo
from database.repos.automod_config_repo import AutomodConfigRepo, AutomodConfigRow


@dataclass(frozen=True)
class AutomodConfig:
    """Configuration automod pour affichage/utilisation."""
    scam_detection_enabled: bool
    spam_detection_enabled: bool
    spam_channel_threshold: int
    spam_time_window: int
    delete_messages_on_scam: bool
    delete_period_hours: int
    whitelisted_roles: List[int]
    whitelisted_channels: List[int]
    custom_scam_patterns: List[str]
    custom_scam_domains: List[str]


class AutomodConfigService:
    """
    Service DB pour la configuration automod.
    """

    # Configuration par défaut
    DEFAULT_CONFIG = AutomodConfig(
        scam_detection_enabled=True,
        spam_detection_enabled=True,
        spam_channel_threshold=3,
        spam_time_window=60,
        delete_messages_on_scam=True,
        delete_period_hours=24,
        whitelisted_roles=[],
        whitelisted_channels=[],
        custom_scam_patterns=[],
        custom_scam_domains=[],
    )

    def __init__(self, db):
        self._db = db

    def _row_to_config(self, row: AutomodConfigRow) -> AutomodConfig:
        return AutomodConfig(
            scam_detection_enabled=row.scam_detection_enabled,
            spam_detection_enabled=row.spam_detection_enabled,
            spam_channel_threshold=row.spam_channel_threshold,
            spam_time_window=row.spam_time_window,
            delete_messages_on_scam=row.delete_messages_on_scam,
            delete_period_hours=row.delete_period_hours,
            whitelisted_roles=row.whitelisted_roles,
            whitelisted_channels=row.whitelisted_channels,
            custom_scam_patterns=row.custom_scam_patterns,
            custom_scam_domains=row.custom_scam_domains,
        )

    async def get_config(self, guild_id: int) -> Optional[AutomodConfig]:
        """
        Récupère la configuration automod pour un serveur.
        Retourne None si aucune config n'existe.
        """
        async with self._db.acquire() as conn:
            row = await AutomodConfigRepo.get(conn, guild_id)
            if not row:
                return None
            return self._row_to_config(row)

    async def get_or_create_config(
        self,
        guild_id: int,
        guild_name: Optional[str] = None,
    ) -> AutomodConfig:
        """
        Récupère ou crée la configuration automod pour un serveur.
        Retourne toujours une config.
        """
        async with self._db.transaction() as conn:
            # Ensure guild exists
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)

            row = await AutomodConfigRepo.upsert(conn, guild_id)
            return self._row_to_config(row)

    async def set_scam_detection(
        self,
        guild_id: int,
        guild_name: Optional[str],
        enabled: bool,
    ) -> bool:
        """Active ou désactive la détection de scam."""
        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            await AutomodConfigRepo.upsert(conn, guild_id)
            return await AutomodConfigRepo.update_field(
                conn, guild_id, "scam_detection_enabled", enabled
            )

    async def set_spam_detection(
        self,
        guild_id: int,
        guild_name: Optional[str],
        enabled: bool,
    ) -> bool:
        """Active ou désactive la détection de spam."""
        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            await AutomodConfigRepo.upsert(conn, guild_id)
            return await AutomodConfigRepo.update_field(
                conn, guild_id, "spam_detection_enabled", enabled
            )

    async def set_spam_threshold(
        self,
        guild_id: int,
        guild_name: Optional[str],
        threshold: int,
    ) -> bool:
        """Définit le seuil de salons pour la détection de spam."""
        if threshold <= 0:
            raise ValueError("threshold must be > 0")
        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            await AutomodConfigRepo.upsert(conn, guild_id)
            return await AutomodConfigRepo.update_field(
                conn, guild_id, "spam_channel_threshold", threshold
            )

    async def set_spam_time_window(
        self,
        guild_id: int,
        guild_name: Optional[str],
        seconds: int,
    ) -> bool:
        """Définit la fenêtre de temps pour la détection de spam."""
        if seconds <= 0:
            raise ValueError("seconds must be > 0")
        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            await AutomodConfigRepo.upsert(conn, guild_id)
            return await AutomodConfigRepo.update_field(
                conn, guild_id, "spam_time_window", seconds
            )

    async def set_delete_messages_on_scam(
        self,
        guild_id: int,
        guild_name: Optional[str],
        enabled: bool,
    ) -> bool:
        """Active ou désactive la suppression des messages de scam."""
        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            await AutomodConfigRepo.upsert(conn, guild_id)
            return await AutomodConfigRepo.update_field(
                conn, guild_id, "delete_messages_on_scam", enabled
            )

    async def set_delete_period_hours(
        self,
        guild_id: int,
        guild_name: Optional[str],
        hours: int,
    ) -> bool:
        """Définit la période de suppression des messages."""
        if hours <= 0:
            raise ValueError("hours must be > 0")
        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            await AutomodConfigRepo.upsert(conn, guild_id)
            return await AutomodConfigRepo.update_field(
                conn, guild_id, "delete_period_hours", hours
            )

    async def add_whitelisted_role(
        self,
        guild_id: int,
        guild_name: Optional[str],
        role_id: int,
    ) -> bool:
        """Ajoute un rôle à la whitelist (si pas déjà présent)."""
        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            await AutomodConfigRepo.upsert(conn, guild_id)
            return await AutomodConfigRepo.array_append(
                conn, guild_id, "whitelisted_roles", role_id
            )

    async def remove_whitelisted_role(
        self,
        guild_id: int,
        role_id: int,
    ) -> bool:
        """Retire un rôle de la whitelist."""
        async with self._db.transaction() as conn:
            return await AutomodConfigRepo.array_remove(
                conn, guild_id, "whitelisted_roles", role_id
            )

    async def add_whitelisted_channel(
        self,
        guild_id: int,
        guild_name: Optional[str],
        channel_id: int,
    ) -> bool:
        """Ajoute un salon à la whitelist (si pas déjà présent)."""
        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            await AutomodConfigRepo.upsert(conn, guild_id)
            return await AutomodConfigRepo.array_append(
                conn, guild_id, "whitelisted_channels", channel_id
            )

    async def remove_whitelisted_channel(
        self,
        guild_id: int,
        channel_id: int,
    ) -> bool:
        """Retire un salon de la whitelist."""
        async with self._db.transaction() as conn:
            return await AutomodConfigRepo.array_remove(
                conn, guild_id, "whitelisted_channels", channel_id
            )

    async def add_custom_pattern(
        self,
        guild_id: int,
        guild_name: Optional[str],
        pattern: str,
    ) -> bool:
        """Ajoute un pattern de scam personnalisé (si pas déjà présent)."""
        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            await AutomodConfigRepo.upsert(conn, guild_id)
            return await AutomodConfigRepo.array_append(
                conn, guild_id, "custom_scam_patterns", pattern
            )

    async def remove_custom_pattern(
        self,
        guild_id: int,
        pattern: str,
    ) -> bool:
        """Retire un pattern de scam personnalisé."""
        async with self._db.transaction() as conn:
            return await AutomodConfigRepo.array_remove(
                conn, guild_id, "custom_scam_patterns", pattern
            )

    async def add_custom_domain(
        self,
        guild_id: int,
        guild_name: Optional[str],
        domain: str,
    ) -> bool:
        """Ajoute un domaine de scam personnalisé (normalisé, si pas déjà présent)."""
        # Normaliser le domaine
        domain = domain.lower().replace("https://", "").replace("http://", "").strip("/")
        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            await AutomodConfigRepo.upsert(conn, guild_id)
            return await AutomodConfigRepo.array_append(
                conn, guild_id, "custom_scam_domains", domain
            )

    async def remove_custom_domain(
        self,
        guild_id: int,
        domain: str,
    ) -> bool:
        """Retire un domaine de scam personnalisé."""
        domain = domain.lower().replace("https://", "").replace("http://", "").strip("/")
        async with self._db.transaction() as conn:
            return await AutomodConfigRepo.array_remove(
                conn, guild_id, "custom_scam_domains", domain
            )
