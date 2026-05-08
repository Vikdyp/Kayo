# database/repos/moderation_role_backups_repo.py
"""
SQL pur pour la table moderation_role_backups.
Un repo = une table. Aucun appel à un autre repo.
"""

import asyncpg
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass(frozen=True)
class RoleBackupRow:
    guild_id: int
    user_id: int
    roles: List[int]
    created_at: datetime


class ModerationRoleBackupsRepo:

    @staticmethod
    async def get(
        conn: asyncpg.Connection,
        guild_id: int,
        user_id: int,
    ) -> Optional[RoleBackupRow]:
        """Récupère le backup des rôles pour un utilisateur."""
        r = await conn.fetchrow(
            """
            SELECT guild_id, user_id, roles, created_at
            FROM moderation_role_backups
            WHERE guild_id = $1 AND user_id = $2;
            """,
            guild_id,
            user_id,
        )
        if not r:
            return None
        return RoleBackupRow(
            guild_id=r["guild_id"],
            user_id=r["user_id"],
            roles=list(r["roles"] or []),
            created_at=r["created_at"],
        )

    @staticmethod
    async def upsert(
        conn: asyncpg.Connection,
        guild_id: int,
        user_id: int,
        roles: List[int],
    ) -> RoleBackupRow:
        """
        Insert ou update le backup des rôles.
        ATTENTION: roles doit être dédupliqué et trié par l'appelant.
        """
        r = await conn.fetchrow(
            """
            INSERT INTO moderation_role_backups (guild_id, user_id, roles)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id, user_id) DO UPDATE
                SET roles = EXCLUDED.roles,
                    created_at = now()
            RETURNING guild_id, user_id, roles, created_at;
            """,
            guild_id,
            user_id,
            roles,
        )
        return RoleBackupRow(
            guild_id=r["guild_id"],
            user_id=r["user_id"],
            roles=list(r["roles"] or []),
            created_at=r["created_at"],
        )

    @staticmethod
    async def delete(
        conn: asyncpg.Connection,
        guild_id: int,
        user_id: int,
    ) -> bool:
        """Supprime le backup des rôles. Retourne True si supprimé."""
        result = await conn.execute(
            """
            DELETE FROM moderation_role_backups
            WHERE guild_id = $1 AND user_id = $2;
            """,
            guild_id,
            user_id,
        )
        return not result.endswith("0")
