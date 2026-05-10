# database/repos/automod_config_repo.py
"""
SQL pur pour la table automod_config.
Un repo = une table. Aucun appel à un autre repo.
Toute mutation met à jour updated_at = now().
"""

import asyncpg
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Any


@dataclass(frozen=True)
class AutomodConfigRow:
    guild_id: int
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
    created_at: datetime
    updated_at: datetime


class AutomodConfigRepo:

    _SCALAR_UPDATE_SQL = {
        "scam_detection_enabled": """
            UPDATE automod_config
            SET scam_detection_enabled = $1, updated_at = now()
            WHERE guild_id = $2;
            """,
        "spam_detection_enabled": """
            UPDATE automod_config
            SET spam_detection_enabled = $1, updated_at = now()
            WHERE guild_id = $2;
            """,
        "spam_channel_threshold": """
            UPDATE automod_config
            SET spam_channel_threshold = $1, updated_at = now()
            WHERE guild_id = $2;
            """,
        "spam_time_window": """
            UPDATE automod_config
            SET spam_time_window = $1, updated_at = now()
            WHERE guild_id = $2;
            """,
        "delete_messages_on_scam": """
            UPDATE automod_config
            SET delete_messages_on_scam = $1, updated_at = now()
            WHERE guild_id = $2;
            """,
        "delete_period_hours": """
            UPDATE automod_config
            SET delete_period_hours = $1, updated_at = now()
            WHERE guild_id = $2;
            """,
    }

    _ARRAY_APPEND_SQL = {
        "whitelisted_roles": """
            UPDATE automod_config
            SET whitelisted_roles = array_append(whitelisted_roles, $1),
                updated_at = now()
            WHERE guild_id = $2
              AND NOT ($1 = ANY(whitelisted_roles));
            """,
        "whitelisted_channels": """
            UPDATE automod_config
            SET whitelisted_channels = array_append(whitelisted_channels, $1),
                updated_at = now()
            WHERE guild_id = $2
              AND NOT ($1 = ANY(whitelisted_channels));
            """,
        "custom_scam_patterns": """
            UPDATE automod_config
            SET custom_scam_patterns = array_append(custom_scam_patterns, $1),
                updated_at = now()
            WHERE guild_id = $2
              AND NOT ($1 = ANY(custom_scam_patterns));
            """,
        "custom_scam_domains": """
            UPDATE automod_config
            SET custom_scam_domains = array_append(custom_scam_domains, $1),
                updated_at = now()
            WHERE guild_id = $2
              AND NOT ($1 = ANY(custom_scam_domains));
            """,
    }

    _ARRAY_REMOVE_SQL = {
        "whitelisted_roles": """
            UPDATE automod_config
            SET whitelisted_roles = array_remove(whitelisted_roles, $1),
                updated_at = now()
            WHERE guild_id = $2;
            """,
        "whitelisted_channels": """
            UPDATE automod_config
            SET whitelisted_channels = array_remove(whitelisted_channels, $1),
                updated_at = now()
            WHERE guild_id = $2;
            """,
        "custom_scam_patterns": """
            UPDATE automod_config
            SET custom_scam_patterns = array_remove(custom_scam_patterns, $1),
                updated_at = now()
            WHERE guild_id = $2;
            """,
        "custom_scam_domains": """
            UPDATE automod_config
            SET custom_scam_domains = array_remove(custom_scam_domains, $1),
                updated_at = now()
            WHERE guild_id = $2;
            """,
    }

    @staticmethod
    async def get(
        conn: asyncpg.Connection,
        guild_id: int,
    ) -> Optional[AutomodConfigRow]:
        """Récupère la configuration automod pour un serveur."""
        r = await conn.fetchrow(
            """
            SELECT guild_id, scam_detection_enabled, spam_detection_enabled,
                   spam_channel_threshold, spam_time_window, delete_messages_on_scam,
                   delete_period_hours, whitelisted_roles, whitelisted_channels,
                   custom_scam_patterns, custom_scam_domains, created_at, updated_at
            FROM automod_config
            WHERE guild_id = $1;
            """,
            guild_id,
        )
        if not r:
            return None
        return AutomodConfigRow(
            guild_id=r["guild_id"],
            scam_detection_enabled=r["scam_detection_enabled"],
            spam_detection_enabled=r["spam_detection_enabled"],
            spam_channel_threshold=r["spam_channel_threshold"],
            spam_time_window=r["spam_time_window"],
            delete_messages_on_scam=r["delete_messages_on_scam"],
            delete_period_hours=r["delete_period_hours"],
            whitelisted_roles=list(r["whitelisted_roles"] or []),
            whitelisted_channels=list(r["whitelisted_channels"] or []),
            custom_scam_patterns=list(r["custom_scam_patterns"] or []),
            custom_scam_domains=list(r["custom_scam_domains"] or []),
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )

    @staticmethod
    async def upsert(
        conn: asyncpg.Connection,
        guild_id: int,
    ) -> AutomodConfigRow:
        """
        Insert ou update la configuration avec les valeurs par défaut.
        Retourne la config (nouvelle ou existante).
        """
        r = await conn.fetchrow(
            """
            INSERT INTO automod_config (guild_id)
            VALUES ($1)
            ON CONFLICT (guild_id) DO UPDATE
                SET updated_at = now()
            RETURNING guild_id, scam_detection_enabled, spam_detection_enabled,
                      spam_channel_threshold, spam_time_window, delete_messages_on_scam,
                      delete_period_hours, whitelisted_roles, whitelisted_channels,
                      custom_scam_patterns, custom_scam_domains, created_at, updated_at;
            """,
            guild_id,
        )
        return AutomodConfigRow(
            guild_id=r["guild_id"],
            scam_detection_enabled=r["scam_detection_enabled"],
            spam_detection_enabled=r["spam_detection_enabled"],
            spam_channel_threshold=r["spam_channel_threshold"],
            spam_time_window=r["spam_time_window"],
            delete_messages_on_scam=r["delete_messages_on_scam"],
            delete_period_hours=r["delete_period_hours"],
            whitelisted_roles=list(r["whitelisted_roles"] or []),
            whitelisted_channels=list(r["whitelisted_channels"] or []),
            custom_scam_patterns=list(r["custom_scam_patterns"] or []),
            custom_scam_domains=list(r["custom_scam_domains"] or []),
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )

    @staticmethod
    async def update_field(
        conn: asyncpg.Connection,
        guild_id: int,
        field: str,
        value: Any,
    ) -> bool:
        """
        Met à jour un champ scalaire de la configuration.
        ATTENTION: field doit être un nom de colonne validé côté appelant.
        Retourne True si la ligne a été mise à jour.
        """
        # Liste blanche des champs autorisés
        query = AutomodConfigRepo._SCALAR_UPDATE_SQL.get(field)
        if query is None:
            raise ValueError(f"Field '{field}' not allowed for update")

        result = await conn.execute(
            query,
            value,
            guild_id,
        )
        return result.endswith("1")

    @staticmethod
    async def array_append(
        conn: asyncpg.Connection,
        guild_id: int,
        field: str,
        value: Any,
    ) -> bool:
        """
        Ajoute une valeur à un array si elle n'existe pas déjà.
        Retourne True si la ligne a été mise à jour.
        """
        query = AutomodConfigRepo._ARRAY_APPEND_SQL.get(field)
        if query is None:
            raise ValueError(f"Field '{field}' not allowed for array_append")

        result = await conn.execute(
            query,
            value,
            guild_id,
        )
        return not result.endswith("0")

    @staticmethod
    async def array_remove(
        conn: asyncpg.Connection,
        guild_id: int,
        field: str,
        value: Any,
    ) -> bool:
        """
        Retire une valeur d'un array.
        Retourne True si la ligne a été mise à jour.
        """
        query = AutomodConfigRepo._ARRAY_REMOVE_SQL.get(field)
        if query is None:
            raise ValueError(f"Field '{field}' not allowed for array_remove")

        result = await conn.execute(
            query,
            value,
            guild_id,
        )
        return result.endswith("1")
