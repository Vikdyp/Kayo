# database/services/message_deletions_service.py
"""
Gestion des transactions pour l'historique des suppressions de messages.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from database.repos.guilds_repo import GuildsRepo
from database.repos.user_repo import UserRepo
from database.repos.message_deletions_repo import MessageDeletionsRepo, MessageDeletionRow


@dataclass(frozen=True)
class MessageDeletionInfo:
    """Info de suppression pour affichage."""
    id: int
    deleted_by_discord_id: Optional[int]  # None si suppression automatique
    source: str  # 'moderator', 'automod', 'system'
    channel_id: int
    channel_name: Optional[str]
    deletion_type: str
    target_user_discord_id: Optional[int]
    target_user_tag: Optional[str]
    message_count: int
    created_at: datetime


class MessageDeletionsService:
    """
    Service DB pour l'historique des suppressions de messages.
    Les API publiques prennent des discord_id et font le mapping en interne.
    """

    def __init__(self, db):
        self._db = db
        # Cache user_id -> discord_id pour éviter des requêtes supplémentaires
        self._discord_id_cache: dict[int, int] = {}

    async def log_deletion(
        self,
        guild_id: int,
        guild_name: Optional[str],
        deleted_by_discord_id: Optional[int],
        channel_id: int,
        channel_name: Optional[str],
        deletion_type: str,
        target_user_discord_id: Optional[int],
        target_user_tag: Optional[str],
        message_count: int,
        source: str = "moderator",
    ) -> int:
        """
        Enregistre une suppression de messages.

        Args:
            guild_id: ID Discord du serveur
            guild_name: Nom du serveur (pour cache)
            deleted_by_discord_id: ID Discord du modérateur (None si automatique)
            channel_id: ID Discord du channel
            channel_name: Nom du channel (snapshot)
            deletion_type: Type de suppression (all, user, number, from, image, gif, links, scam, spam...)
            target_user_discord_id: ID Discord de l'utilisateur ciblé (si applicable)
            target_user_tag: Tag de l'utilisateur ciblé (snapshot)
            message_count: Nombre de messages supprimés
            source: Source de la suppression ('moderator', 'automod', 'system')

        Returns:
            ID de l'entrée créée
        """
        async with self._db.transaction() as conn:
            # Ensure guild exists
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)

            # Convert discord_id -> user_id (if provided)
            deleted_by_user_id = None
            if deleted_by_discord_id is not None:
                deleted_by_user_id = await UserRepo.ensure_exists(conn, discord_id=deleted_by_discord_id)

            target_user_id = None
            if target_user_discord_id is not None:
                target_user_id = await UserRepo.ensure_exists(conn, discord_id=target_user_discord_id)

            return await MessageDeletionsRepo.insert(
                conn,
                guild_id=guild_id,
                deleted_by_user_id=deleted_by_user_id,
                source=source,
                channel_id=channel_id,
                channel_name=channel_name,
                deletion_type=deletion_type,
                target_user_id=target_user_id,
                target_user_tag=target_user_tag,
                message_count=message_count,
            )

    async def get_recent_deletions(
        self,
        guild_id: int,
        limit: int = 50,
    ) -> List[MessageDeletionInfo]:
        """
        Récupère les suppressions récentes pour un serveur.

        Args:
            guild_id: ID Discord du serveur
            limit: Nombre maximum d'entrées (max 100)

        Returns:
            Liste des suppressions avec discord_id convertis
        """
        limit = min(limit, 100)  # Cap à 100

        async with self._db.acquire() as conn:
            rows = await MessageDeletionsRepo.list_recent(conn, guild_id, limit)

            if not rows:
                return []

            # Collect all user_ids to fetch discord_ids in batch
            user_ids = set()
            for row in rows:
                if row.deleted_by_user_id is not None:
                    user_ids.add(row.deleted_by_user_id)
                if row.target_user_id is not None:
                    user_ids.add(row.target_user_id)

            # Fetch discord_ids for all users
            user_id_to_discord_id = await self._get_discord_ids_batch(conn, user_ids)

            return [
                MessageDeletionInfo(
                    id=row.id,
                    deleted_by_discord_id=user_id_to_discord_id.get(row.deleted_by_user_id) if row.deleted_by_user_id else None,
                    source=row.source,
                    channel_id=row.channel_id,
                    channel_name=row.channel_name,
                    deletion_type=row.deletion_type,
                    target_user_discord_id=user_id_to_discord_id.get(row.target_user_id) if row.target_user_id else None,
                    target_user_tag=row.target_user_tag,
                    message_count=row.message_count,
                    created_at=row.created_at,
                )
                for row in rows
            ]

    async def _get_discord_ids_batch(
        self,
        conn,
        user_ids: set[int],
    ) -> dict[int, int]:
        """Récupère les discord_ids pour un ensemble de user_ids."""
        if not user_ids:
            return {}

        return await UserRepo.get_discord_ids_by_user_ids(conn, list(user_ids))
