# database/services/unban_requests_service.py
"""
Gestion des transactions pour les demandes de déban.
Toutes les méthodes publiques prennent des discord_id et font le mapping interne.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from database.repos.guilds_repo import GuildsRepo
from database.repos.user_repo import UserRepo
from database.repos.unban_requests_repo import UnbanRequestsRepo


@dataclass(frozen=True)
class UnbanRequestInfo:
    """Information sur une demande de déban pour affichage/utilisation."""
    id: int
    guild_id: int
    requester_discord_id: int
    channel_id: int
    message_id: int
    reason: Optional[str]
    status: str
    created_at: datetime
    resolved_at: Optional[datetime]
    resolved_by_discord_id: Optional[int]


class UnbanRequestsService:
    """
    Service DB pour les demandes de déban.
    Reçoit l'instance DB en injection.
    """

    def __init__(self, db):
        self._db = db

    async def create_request(
        self,
        guild_id: int,
        guild_name: Optional[str],
        requester_discord_id: int,
        channel_id: int,
        message_id: int,
        reason: Optional[str],
    ) -> UnbanRequestInfo:
        """
        Crée une nouvelle demande de déban.
        """
        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            requester_user_id = await UserRepo.ensure_exists(conn, discord_id=requester_discord_id)

            row = await UnbanRequestsRepo.insert(
                conn,
                guild_id=guild_id,
                requester_user_id=requester_user_id,
                channel_id=channel_id,
                message_id=message_id,
                reason=reason,
            )

            return UnbanRequestInfo(
                id=row.id,
                guild_id=row.guild_id,
                requester_discord_id=requester_discord_id,
                channel_id=row.channel_id,
                message_id=row.message_id,
                reason=row.reason,
                status=row.status,
                created_at=row.created_at,
                resolved_at=row.resolved_at,
                resolved_by_discord_id=None,
            )

    async def get_by_message_id(self, message_id: int) -> Optional[UnbanRequestInfo]:
        """Récupère une demande par message_id."""
        async with self._db.acquire() as conn:
            row = await UnbanRequestsRepo.get_by_message_id(conn, message_id)
            if not row:
                return None

            # Get discord_ids
            requester = await UserRepo.get_by_user_id(conn, row.requester_user_id)
            resolved_by_discord_id = None
            if row.resolved_by_user_id:
                resolved_by = await UserRepo.get_by_user_id(conn, row.resolved_by_user_id)
                resolved_by_discord_id = resolved_by.discord_id if resolved_by else None

            return UnbanRequestInfo(
                id=row.id,
                guild_id=row.guild_id,
                requester_discord_id=requester.discord_id if requester else 0,
                channel_id=row.channel_id,
                message_id=row.message_id,
                reason=row.reason,
                status=row.status,
                created_at=row.created_at,
                resolved_at=row.resolved_at,
                resolved_by_discord_id=resolved_by_discord_id,
            )

    async def has_pending_request(
        self,
        guild_id: int,
        requester_discord_id: int,
    ) -> bool:
        """Vérifie si l'utilisateur a une demande en cours."""
        async with self._db.acquire() as conn:
            user = await UserRepo.get_by_discord_id(conn, requester_discord_id)
            if not user:
                return False

            row = await UnbanRequestsRepo.get_pending_for_user(
                conn, guild_id, user.user_id
            )
            return row is not None

    async def list_pending(self, guild_id: int) -> List[UnbanRequestInfo]:
        """Liste toutes les demandes en cours pour un serveur."""
        async with self._db.acquire() as conn:
            rows = await UnbanRequestsRepo.list_pending(conn, guild_id)

            result = []
            for row in rows:
                requester = await UserRepo.get_by_user_id(conn, row.requester_user_id)
                result.append(UnbanRequestInfo(
                    id=row.id,
                    guild_id=row.guild_id,
                    requester_discord_id=requester.discord_id if requester else 0,
                    channel_id=row.channel_id,
                    message_id=row.message_id,
                    reason=row.reason,
                    status=row.status,
                    created_at=row.created_at,
                    resolved_at=row.resolved_at,
                    resolved_by_discord_id=None,
                ))

            return result

    async def accept(
        self,
        request_id: int,
        resolved_by_discord_id: int,
    ) -> bool:
        """
        Accepte une demande de déban.
        Retourne True si la mise à jour a été effectuée.
        """
        async with self._db.transaction() as conn:
            resolved_by_user_id = await UserRepo.ensure_exists(
                conn, discord_id=resolved_by_discord_id
            )
            return await UnbanRequestsRepo.resolve(
                conn, request_id, 'accepted', resolved_by_user_id
            )

    async def reject(
        self,
        request_id: int,
        resolved_by_discord_id: int,
    ) -> bool:
        """
        Rejette une demande de déban.
        Retourne True si la mise à jour a été effectuée.
        """
        async with self._db.transaction() as conn:
            resolved_by_user_id = await UserRepo.ensure_exists(
                conn, discord_id=resolved_by_discord_id
            )
            return await UnbanRequestsRepo.resolve(
                conn, request_id, 'rejected', resolved_by_user_id
            )

    async def delete(self, request_id: int) -> bool:
        """Supprime une demande."""
        async with self._db.transaction() as conn:
            return await UnbanRequestsRepo.delete(conn, request_id)

    async def delete_by_message_id(self, message_id: int) -> bool:
        """Supprime une demande par message_id."""
        async with self._db.transaction() as conn:
            return await UnbanRequestsRepo.delete_by_message_id(conn, message_id)
