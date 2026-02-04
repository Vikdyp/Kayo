# database/repos/moderation_warnings_repo.py
"""
SQL pur pour la table moderation_warnings.
Un repo = une table. Aucun appel à un autre repo.
"""

import asyncpg
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass(frozen=True)
class WarningRow:
    id: int
    guild_id: int
    user_id: int
    warned_by_user_id: int
    reason: Optional[str]
    created_at: datetime


class ModerationWarningsRepo:

    @staticmethod
    async def insert(
        conn: asyncpg.Connection,
        guild_id: int,
        user_id: int,
        warned_by_user_id: int,
        reason: Optional[str],
    ) -> int:
        """Insère un warning et retourne l'ID."""
        row = await conn.fetchrow(
            """
            INSERT INTO moderation_warnings (guild_id, user_id, warned_by_user_id, reason)
            VALUES ($1, $2, $3, $4)
            RETURNING id;
            """,
            guild_id,
            user_id,
            warned_by_user_id,
            reason,
        )
        return int(row["id"])

    @staticmethod
    async def count_for_user(
        conn: asyncpg.Connection,
        guild_id: int,
        user_id: int,
    ) -> int:
        """Compte les warnings pour un utilisateur dans un serveur."""
        row = await conn.fetchrow(
            """
            SELECT COUNT(*) as count
            FROM moderation_warnings
            WHERE guild_id = $1 AND user_id = $2;
            """,
            guild_id,
            user_id,
        )
        return int(row["count"])

    @staticmethod
    async def list_for_user(
        conn: asyncpg.Connection,
        guild_id: int,
        user_id: int,
        limit: int = 50,
    ) -> List[WarningRow]:
        """Liste les warnings pour un utilisateur dans un serveur."""
        rows = await conn.fetch(
            """
            SELECT id, guild_id, user_id, warned_by_user_id, reason, created_at
            FROM moderation_warnings
            WHERE guild_id = $1 AND user_id = $2
            ORDER BY created_at DESC
            LIMIT $3;
            """,
            guild_id,
            user_id,
            limit,
        )
        return [
            WarningRow(
                id=r["id"],
                guild_id=r["guild_id"],
                user_id=r["user_id"],
                warned_by_user_id=r["warned_by_user_id"],
                reason=r["reason"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    @staticmethod
    async def delete(
        conn: asyncpg.Connection,
        warning_id: int,
    ) -> bool:
        """Supprime un warning par ID. Retourne True si supprimé."""
        result = await conn.execute(
            """
            DELETE FROM moderation_warnings
            WHERE id = $1;
            """,
            warning_id,
        )
        return not result.endswith("0")

    @staticmethod
    async def clear_for_user(
        conn: asyncpg.Connection,
        guild_id: int,
        user_id: int,
    ) -> int:
        """Supprime tous les warnings d'un utilisateur. Retourne le nombre supprimé."""
        result = await conn.execute(
            """
            DELETE FROM moderation_warnings
            WHERE guild_id = $1 AND user_id = $2;
            """,
            guild_id,
            user_id,
        )
        # Extract count from "DELETE X"
        try:
            return int(result.split()[-1])
        except (ValueError, IndexError):
            return 0
