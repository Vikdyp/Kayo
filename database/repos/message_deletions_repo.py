# database/repos/message_deletions_repo.py
"""
SQL pur pour la table message_deletions.
Un repo = une table. Aucun appel à un autre repo.
"""

import asyncpg
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass(frozen=True)
class MessageDeletionRow:
    id: int
    guild_id: int
    deleted_by_user_id: Optional[int]  # NULL si suppression automatique
    source: str  # 'moderator', 'automod', 'system'
    channel_id: int
    channel_name: Optional[str]
    deletion_type: str
    target_user_id: Optional[int]
    target_user_tag: Optional[str]
    message_count: int
    created_at: datetime


class MessageDeletionsRepo:

    @staticmethod
    async def insert(
        conn: asyncpg.Connection,
        guild_id: int,
        deleted_by_user_id: Optional[int],
        source: str,
        channel_id: int,
        channel_name: Optional[str],
        deletion_type: str,
        target_user_id: Optional[int],
        target_user_tag: Optional[str],
        message_count: int,
    ) -> int:
        """Insère une entrée de suppression et retourne l'ID."""
        row = await conn.fetchrow(
            """
            INSERT INTO message_deletions (
                guild_id, deleted_by_user_id, source, channel_id, channel_name,
                deletion_type, target_user_id, target_user_tag, message_count
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING id;
            """,
            guild_id,
            deleted_by_user_id,
            source,
            channel_id,
            channel_name,
            deletion_type,
            target_user_id,
            target_user_tag,
            message_count,
        )
        return int(row["id"])

    @staticmethod
    async def list_recent(
        conn: asyncpg.Connection,
        guild_id: int,
        limit: int = 50,
    ) -> List[MessageDeletionRow]:
        """Liste les suppressions récentes pour un serveur."""
        rows = await conn.fetch(
            """
            SELECT id, guild_id, deleted_by_user_id, source, channel_id, channel_name,
                   deletion_type, target_user_id, target_user_tag, message_count, created_at
            FROM message_deletions
            WHERE guild_id = $1
            ORDER BY created_at DESC
            LIMIT $2;
            """,
            guild_id,
            limit,
        )
        return [
            MessageDeletionRow(
                id=r["id"],
                guild_id=r["guild_id"],
                deleted_by_user_id=r["deleted_by_user_id"],
                source=r["source"],
                channel_id=r["channel_id"],
                channel_name=r["channel_name"],
                deletion_type=r["deletion_type"],
                target_user_id=r["target_user_id"],
                target_user_tag=r["target_user_tag"],
                message_count=r["message_count"],
                created_at=r["created_at"],
            )
            for r in rows
        ]
