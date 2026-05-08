# database/repos/persistent_messages_repo.py
"""
SQL pur pour la table persistent_messages.
Un repo = une table. Aucun appel à un autre repo.
"""

import asyncpg
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PersistentMessageRow:
    guild_id: int
    message_type: str
    channel_id: int
    message_id: int


class PersistentMessagesRepo:

    @staticmethod
    async def get(
        conn: asyncpg.Connection,
        guild_id: int,
        message_type: str,
    ) -> Optional[PersistentMessageRow]:
        """Récupère un message persistant par type."""
        r = await conn.fetchrow(
            """
            SELECT guild_id, message_type, channel_id, message_id
            FROM persistent_messages
            WHERE guild_id = $1 AND message_type = $2;
            """,
            guild_id,
            message_type,
        )
        if not r:
            return None
        return PersistentMessageRow(
            guild_id=r["guild_id"],
            message_type=r["message_type"],
            channel_id=r["channel_id"],
            message_id=r["message_id"],
        )

    @staticmethod
    async def upsert(
        conn: asyncpg.Connection,
        guild_id: int,
        message_type: str,
        channel_id: int,
        message_id: int,
    ) -> None:
        """Insert ou update un message persistant."""
        await conn.execute(
            """
            INSERT INTO persistent_messages (guild_id, message_type, channel_id, message_id)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id, message_type) DO UPDATE
                SET channel_id = EXCLUDED.channel_id,
                    message_id = EXCLUDED.message_id,
                    updated_at = now();
            """,
            guild_id,
            message_type,
            channel_id,
            message_id,
        )

    @staticmethod
    async def delete(
        conn: asyncpg.Connection,
        guild_id: int,
        message_type: str,
    ) -> bool:
        """Supprime un message persistant. Retourne True si supprimé."""
        res = await conn.execute(
            """
            DELETE FROM persistent_messages
            WHERE guild_id = $1 AND message_type = $2;
            """,
            guild_id,
            message_type,
        )
        return res.startswith("DELETE ") and not res.endswith(" 0")
