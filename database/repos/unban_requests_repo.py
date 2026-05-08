# database/repos/unban_requests_repo.py
"""
SQL pur pour la table unban_requests.
Un repo = une table. Aucun appel à un autre repo.
"""

import asyncpg
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass(frozen=True)
class UnbanRequestRow:
    id: int
    guild_id: int
    requester_user_id: int
    channel_id: int
    message_id: int
    reason: Optional[str]
    status: str
    created_at: datetime
    resolved_at: Optional[datetime]
    resolved_by_user_id: Optional[int]


class UnbanRequestsRepo:

    @staticmethod
    async def insert(
        conn: asyncpg.Connection,
        guild_id: int,
        requester_user_id: int,
        channel_id: int,
        message_id: int,
        reason: Optional[str],
    ) -> UnbanRequestRow:
        """Insère une nouvelle demande de déban."""
        r = await conn.fetchrow(
            """
            INSERT INTO unban_requests (guild_id, requester_user_id, channel_id, message_id, reason)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id, guild_id, requester_user_id, channel_id, message_id, reason,
                      status, created_at, resolved_at, resolved_by_user_id;
            """,
            guild_id,
            requester_user_id,
            channel_id,
            message_id,
            reason,
        )
        return UnbanRequestRow(
            id=r["id"],
            guild_id=r["guild_id"],
            requester_user_id=r["requester_user_id"],
            channel_id=r["channel_id"],
            message_id=r["message_id"],
            reason=r["reason"],
            status=r["status"],
            created_at=r["created_at"],
            resolved_at=r["resolved_at"],
            resolved_by_user_id=r["resolved_by_user_id"],
        )

    @staticmethod
    async def get_by_message_id(
        conn: asyncpg.Connection,
        message_id: int,
    ) -> Optional[UnbanRequestRow]:
        """Récupère une demande par message_id."""
        r = await conn.fetchrow(
            """
            SELECT id, guild_id, requester_user_id, channel_id, message_id, reason,
                   status, created_at, resolved_at, resolved_by_user_id
            FROM unban_requests
            WHERE message_id = $1;
            """,
            message_id,
        )
        if not r:
            return None
        return UnbanRequestRow(
            id=r["id"],
            guild_id=r["guild_id"],
            requester_user_id=r["requester_user_id"],
            channel_id=r["channel_id"],
            message_id=r["message_id"],
            reason=r["reason"],
            status=r["status"],
            created_at=r["created_at"],
            resolved_at=r["resolved_at"],
            resolved_by_user_id=r["resolved_by_user_id"],
        )

    @staticmethod
    async def get_pending_for_user(
        conn: asyncpg.Connection,
        guild_id: int,
        requester_user_id: int,
    ) -> Optional[UnbanRequestRow]:
        """Récupère la demande en cours pour un utilisateur."""
        r = await conn.fetchrow(
            """
            SELECT id, guild_id, requester_user_id, channel_id, message_id, reason,
                   status, created_at, resolved_at, resolved_by_user_id
            FROM unban_requests
            WHERE guild_id = $1 AND requester_user_id = $2 AND status = 'pending';
            """,
            guild_id,
            requester_user_id,
        )
        if not r:
            return None
        return UnbanRequestRow(
            id=r["id"],
            guild_id=r["guild_id"],
            requester_user_id=r["requester_user_id"],
            channel_id=r["channel_id"],
            message_id=r["message_id"],
            reason=r["reason"],
            status=r["status"],
            created_at=r["created_at"],
            resolved_at=r["resolved_at"],
            resolved_by_user_id=r["resolved_by_user_id"],
        )

    @staticmethod
    async def list_pending(
        conn: asyncpg.Connection,
        guild_id: int,
    ) -> List[UnbanRequestRow]:
        """Liste toutes les demandes en cours pour un serveur."""
        rows = await conn.fetch(
            """
            SELECT id, guild_id, requester_user_id, channel_id, message_id, reason,
                   status, created_at, resolved_at, resolved_by_user_id
            FROM unban_requests
            WHERE guild_id = $1 AND status = 'pending'
            ORDER BY created_at ASC;
            """,
            guild_id,
        )
        return [
            UnbanRequestRow(
                id=r["id"],
                guild_id=r["guild_id"],
                requester_user_id=r["requester_user_id"],
                channel_id=r["channel_id"],
                message_id=r["message_id"],
                reason=r["reason"],
                status=r["status"],
                created_at=r["created_at"],
                resolved_at=r["resolved_at"],
                resolved_by_user_id=r["resolved_by_user_id"],
            )
            for r in rows
        ]

    @staticmethod
    async def resolve(
        conn: asyncpg.Connection,
        request_id: int,
        status: str,
        resolved_by_user_id: int,
    ) -> bool:
        """
        Résout une demande (accepted/rejected).
        Retourne True si mise à jour effectuée.
        """
        if status not in ('accepted', 'rejected'):
            raise ValueError(f"Invalid status: {status}")

        result = await conn.execute(
            """
            UPDATE unban_requests
            SET status = $1, resolved_at = now(), resolved_by_user_id = $2
            WHERE id = $3 AND status = 'pending';
            """,
            status,
            resolved_by_user_id,
            request_id,
        )
        return not result.endswith("0")

    @staticmethod
    async def delete(
        conn: asyncpg.Connection,
        request_id: int,
    ) -> bool:
        """Supprime une demande. Retourne True si supprimée."""
        result = await conn.execute(
            """
            DELETE FROM unban_requests
            WHERE id = $1;
            """,
            request_id,
        )
        return not result.endswith("0")

    @staticmethod
    async def delete_by_message_id(
        conn: asyncpg.Connection,
        message_id: int,
    ) -> bool:
        """Supprime une demande par message_id. Retourne True si supprimée."""
        result = await conn.execute(
            """
            DELETE FROM unban_requests
            WHERE message_id = $1;
            """,
            message_id,
        )
        return not result.endswith("0")
