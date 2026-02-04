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
        allowed_fields = {
            "scam_detection_enabled",
            "spam_detection_enabled",
            "spam_channel_threshold",
            "spam_time_window",
            "delete_messages_on_scam",
            "delete_period_hours",
        }
        if field not in allowed_fields:
            raise ValueError(f"Field '{field}' not allowed for update")

        result = await conn.execute(
            f"""
            UPDATE automod_config
            SET {field} = $1, updated_at = now()
            WHERE guild_id = $2;
            """,
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
        allowed_fields = {
            "whitelisted_roles",
            "whitelisted_channels",
            "custom_scam_patterns",
            "custom_scam_domains",
        }
        if field not in allowed_fields:
            raise ValueError(f"Field '{field}' not allowed for array_append")

        result = await conn.execute(
            f"""
            UPDATE automod_config
            SET {field} = array_append({field}, $1),
                updated_at = now()
            WHERE guild_id = $2
              AND NOT ($1 = ANY({field}));
            """,
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
        allowed_fields = {
            "whitelisted_roles",
            "whitelisted_channels",
            "custom_scam_patterns",
            "custom_scam_domains",
        }
        if field not in allowed_fields:
            raise ValueError(f"Field '{field}' not allowed for array_remove")

        result = await conn.execute(
            f"""
            UPDATE automod_config
            SET {field} = array_remove({field}, $1),
                updated_at = now()
            WHERE guild_id = $2;
            """,
            value,
            guild_id,
        )
        return result.endswith("1")
