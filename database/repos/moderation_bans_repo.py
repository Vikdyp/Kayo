# database/repos/moderation_bans_repo.py
"""
SQL pur pour la table moderation_bans.
Un repo = une table. Aucun appel à un autre repo.
"""

import asyncpg
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass(frozen=True)
class BanRow:
    id: int
    guild_id: int
    user_id: int
    ban_type: str
    reason: Optional[str]
    banned_by_user_id: int
    banned_at: datetime
    ban_end: Optional[datetime]


class ModerationBansRepo:

    @staticmethod
    async def get(
        conn: asyncpg.Connection,
        guild_id: int,
        user_id: int,
    ) -> Optional[BanRow]:
        """Récupère un ban pour un utilisateur dans un serveur."""
        r = await conn.fetchrow(
            """
            SELECT id, guild_id, user_id, ban_type, reason,
                   banned_by_user_id, banned_at, ban_end
            FROM moderation_bans
            WHERE guild_id = $1 AND user_id = $2;
            """,
            guild_id,
            user_id,
        )
        if not r:
            return None
        return BanRow(
            id=r["id"],
            guild_id=r["guild_id"],
            user_id=r["user_id"],
            ban_type=r["ban_type"],
            reason=r["reason"],
            banned_by_user_id=r["banned_by_user_id"],
            banned_at=r["banned_at"],
            ban_end=r["ban_end"],
        )

    @staticmethod
    async def upsert(
        conn: asyncpg.Connection,
        guild_id: int,
        user_id: int,
        ban_type: str,
        reason: Optional[str],
        banned_by_user_id: int,
        ban_end: Optional[datetime],
    ) -> BanRow:
        """Insert ou update un ban. Retourne le ban créé/mis à jour."""
        r = await conn.fetchrow(
            """
            INSERT INTO moderation_bans (guild_id, user_id, ban_type, reason, banned_by_user_id, ban_end)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (guild_id, user_id) DO UPDATE
                SET ban_type = EXCLUDED.ban_type,
                    reason = EXCLUDED.reason,
                    banned_by_user_id = EXCLUDED.banned_by_user_id,
                    banned_at = now(),
                    ban_end = EXCLUDED.ban_end
            RETURNING id, guild_id, user_id, ban_type, reason, banned_by_user_id, banned_at, ban_end;
            """,
            guild_id,
            user_id,
            ban_type,
            reason,
            banned_by_user_id,
            ban_end,
        )
        return BanRow(
            id=r["id"],
            guild_id=r["guild_id"],
            user_id=r["user_id"],
            ban_type=r["ban_type"],
            reason=r["reason"],
            banned_by_user_id=r["banned_by_user_id"],
            banned_at=r["banned_at"],
            ban_end=r["ban_end"],
        )

    @staticmethod
    async def delete(
        conn: asyncpg.Connection,
        guild_id: int,
        user_id: int,
    ) -> bool:
        """Supprime un ban. Retourne True si supprimé."""
        result = await conn.execute(
            """
            DELETE FROM moderation_bans
            WHERE guild_id = $1 AND user_id = $2;
            """,
            guild_id,
            user_id,
        )
        return not result.endswith("0")

    @staticmethod
    async def list_expired(
        conn: asyncpg.Connection,
        now: datetime,
    ) -> List[BanRow]:
        """Liste les bans temporaires expirés."""
        rows = await conn.fetch(
            """
            SELECT id, guild_id, user_id, ban_type, reason,
                   banned_by_user_id, banned_at, ban_end
            FROM moderation_bans
            WHERE ban_end IS NOT NULL AND ban_end <= $1;
            """,
            now,
        )
        return [
            BanRow(
                id=r["id"],
                guild_id=r["guild_id"],
                user_id=r["user_id"],
                ban_type=r["ban_type"],
                reason=r["reason"],
                banned_by_user_id=r["banned_by_user_id"],
                banned_at=r["banned_at"],
                ban_end=r["ban_end"],
            )
            for r in rows
        ]
