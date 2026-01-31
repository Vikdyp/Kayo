# database/services/persistent_messages_service.py
"""
Gestion des transactions pour les messages persistants.
"""

from dataclasses import dataclass
from typing import Optional

from database.repos.guilds_repo import GuildsRepo
from database.repos.persistent_messages_repo import PersistentMessagesRepo


@dataclass(frozen=True)
class PersistentMessageInfo:
    channel_id: int
    message_id: int


class PersistentMessagesService:
    """
    Service DB pour les messages persistants Discord.
    """

    def __init__(self, db):
        self._db = db

    async def get(
        self,
        guild_id: int,
        message_type: str,
    ) -> Optional[PersistentMessageInfo]:
        """Récupère un message persistant."""
        async with self._db.acquire() as conn:
            row = await PersistentMessagesRepo.get(conn, guild_id, message_type)
            if not row:
                return None
            return PersistentMessageInfo(
                channel_id=row.channel_id,
                message_id=row.message_id,
            )

    async def save(
        self,
        guild_id: int,
        guild_name: Optional[str],
        message_type: str,
        channel_id: int,
        message_id: int,
    ) -> None:
        """Enregistre ou met à jour un message persistant."""
        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            await PersistentMessagesRepo.upsert(
                conn, guild_id, message_type, channel_id, message_id
            )

    async def delete(self, guild_id: int, message_type: str) -> bool:
        """Supprime un message persistant."""
        async with self._db.transaction() as conn:
            return await PersistentMessagesRepo.delete(conn, guild_id, message_type)
