# database/services/moderation_service.py
"""
Gestion des transactions pour la modération: bans, warnings, role backups.
Toutes les méthodes publiques prennent des discord_id et font le mapping interne.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from database.repos.guilds_repo import GuildsRepo
from database.repos.user_repo import UserRepo
from database.repos.moderation_bans_repo import ModerationBansRepo, BanRow
from database.repos.moderation_warnings_repo import ModerationWarningsRepo, WarningRow
from database.repos.moderation_role_backups_repo import ModerationRoleBackupsRepo


@dataclass(frozen=True)
class BanInfo:
    """Information sur un ban pour affichage/utilisation."""
    id: int
    guild_id: int
    target_discord_id: int
    ban_type: str
    reason: Optional[str]
    moderator_discord_id: int
    banned_at: datetime
    ban_end: Optional[datetime]


@dataclass(frozen=True)
class WarningInfo:
    """Information sur un warning pour affichage/utilisation."""
    id: int
    guild_id: int
    target_discord_id: int
    moderator_discord_id: int
    reason: Optional[str]
    created_at: datetime


class ModerationDbService:
    """
    Service DB pour la modération (bans, warnings, role backups).
    Reçoit l'instance DB en injection.
    """

    def __init__(self, db):
        self._db = db

    # ==================== BANS ====================

    async def get_ban(
        self,
        guild_id: int,
        target_discord_id: int,
    ) -> Optional[BanInfo]:
        """Récupère un ban actif pour un utilisateur."""
        async with self._db.acquire() as conn:
            # Get internal user_id
            user_row = await UserRepo.get_by_discord_id(conn, target_discord_id)
            if not user_row:
                return None

            ban = await ModerationBansRepo.get(conn, guild_id, user_row.user_id)
            if not ban:
                return None

            # Get moderator discord_id
            mod_row = await UserRepo.get_by_user_id(conn, ban.banned_by_user_id)
            mod_discord_id = mod_row.discord_id if mod_row else 0

            return BanInfo(
                id=ban.id,
                guild_id=ban.guild_id,
                target_discord_id=target_discord_id,
                ban_type=ban.ban_type,
                reason=ban.reason,
                moderator_discord_id=mod_discord_id,
                banned_at=ban.banned_at,
                ban_end=ban.ban_end,
            )

    async def add_ban(
        self,
        guild_id: int,
        guild_name: Optional[str],
        target_discord_id: int,
        moderator_discord_id: int,
        ban_type: str,
        reason: Optional[str],
        ban_end: Optional[datetime],
    ) -> BanInfo:
        """
        Ajoute ou met à jour un ban.

        Raises:
            ValueError: Si ban_type='temp' sans ban_end, ou ban_type='perm'/'soft' avec ban_end.
        """
        # Validation cohérence ban_type / ban_end
        if ban_type == 'temp' and ban_end is None:
            raise ValueError("ban_type='temp' requires ban_end")
        if ban_type in ('perm', 'soft') and ban_end is not None:
            raise ValueError(f"ban_type='{ban_type}' must have ban_end=None")

        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            target_user_id = await UserRepo.ensure_exists(conn, discord_id=target_discord_id)
            moderator_user_id = await UserRepo.ensure_exists(conn, discord_id=moderator_discord_id)

            ban = await ModerationBansRepo.upsert(
                conn,
                guild_id=guild_id,
                user_id=target_user_id,
                ban_type=ban_type,
                reason=reason,
                banned_by_user_id=moderator_user_id,
                ban_end=ban_end,
            )

            return BanInfo(
                id=ban.id,
                guild_id=ban.guild_id,
                target_discord_id=target_discord_id,
                ban_type=ban.ban_type,
                reason=ban.reason,
                moderator_discord_id=moderator_discord_id,
                banned_at=ban.banned_at,
                ban_end=ban.ban_end,
            )

    async def remove_ban(
        self,
        guild_id: int,
        target_discord_id: int,
    ) -> bool:
        """Supprime un ban. Retourne True si supprimé."""
        async with self._db.transaction() as conn:
            user_row = await UserRepo.get_by_discord_id(conn, target_discord_id)
            if not user_row:
                return False

            return await ModerationBansRepo.delete(conn, guild_id, user_row.user_id)

    async def get_expired_bans(self, now: datetime) -> List[BanInfo]:
        """Récupère tous les bans expirés."""
        async with self._db.acquire() as conn:
            expired = await ModerationBansRepo.list_expired(conn, now)

            result = []
            for ban in expired:
                # Get discord_ids
                target_row = await UserRepo.get_by_user_id(conn, ban.user_id)
                mod_row = await UserRepo.get_by_user_id(conn, ban.banned_by_user_id)

                result.append(BanInfo(
                    id=ban.id,
                    guild_id=ban.guild_id,
                    target_discord_id=target_row.discord_id if target_row else 0,
                    ban_type=ban.ban_type,
                    reason=ban.reason,
                    moderator_discord_id=mod_row.discord_id if mod_row else 0,
                    banned_at=ban.banned_at,
                    ban_end=ban.ban_end,
                ))

            return result

    # ==================== WARNINGS ====================

    async def add_warning(
        self,
        guild_id: int,
        guild_name: Optional[str],
        target_discord_id: int,
        moderator_discord_id: int,
        reason: Optional[str],
    ) -> int:
        """Ajoute un warning. Retourne l'ID du warning créé."""
        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            target_user_id = await UserRepo.ensure_exists(conn, discord_id=target_discord_id)
            moderator_user_id = await UserRepo.ensure_exists(conn, discord_id=moderator_discord_id)

            return await ModerationWarningsRepo.insert(
                conn,
                guild_id=guild_id,
                user_id=target_user_id,
                warned_by_user_id=moderator_user_id,
                reason=reason,
            )

    async def get_warning_count(
        self,
        guild_id: int,
        target_discord_id: int,
    ) -> int:
        """Compte les warnings pour un utilisateur."""
        async with self._db.acquire() as conn:
            user_row = await UserRepo.get_by_discord_id(conn, target_discord_id)
            if not user_row:
                return 0

            return await ModerationWarningsRepo.count_for_user(
                conn, guild_id, user_row.user_id
            )

    async def list_warnings(
        self,
        guild_id: int,
        target_discord_id: int,
        limit: int = 50,
    ) -> List[WarningInfo]:
        """Liste les warnings pour un utilisateur."""
        async with self._db.acquire() as conn:
            user_row = await UserRepo.get_by_discord_id(conn, target_discord_id)
            if not user_row:
                return []

            warnings = await ModerationWarningsRepo.list_for_user(
                conn, guild_id, user_row.user_id, limit
            )

            result = []
            for w in warnings:
                mod_row = await UserRepo.get_by_user_id(conn, w.warned_by_user_id)
                result.append(WarningInfo(
                    id=w.id,
                    guild_id=w.guild_id,
                    target_discord_id=target_discord_id,
                    moderator_discord_id=mod_row.discord_id if mod_row else 0,
                    reason=w.reason,
                    created_at=w.created_at,
                ))

            return result

    async def delete_warning(self, warning_id: int) -> bool:
        """Supprime un warning par ID. Retourne True si supprimé."""
        async with self._db.transaction() as conn:
            return await ModerationWarningsRepo.delete(conn, warning_id)

    async def clear_warnings(
        self,
        guild_id: int,
        target_discord_id: int,
    ) -> int:
        """Supprime tous les warnings d'un utilisateur. Retourne le nombre supprimé."""
        async with self._db.transaction() as conn:
            user_row = await UserRepo.get_by_discord_id(conn, target_discord_id)
            if not user_row:
                return 0

            return await ModerationWarningsRepo.clear_for_user(
                conn, guild_id, user_row.user_id
            )

    # ==================== ROLE BACKUPS ====================

    async def save_roles(
        self,
        guild_id: int,
        guild_name: Optional[str],
        target_discord_id: int,
        roles: List[int],
    ) -> bool:
        """
        Sauvegarde les rôles d'un utilisateur.
        Les rôles sont dédupliqués et triés.
        Si la liste est vide, supprime le backup existant.
        Retourne True si l'opération a réussi.
        """
        # Dédupliquer et trier
        roles = sorted(set(roles))

        # Liste vide = suppression
        if not roles:
            return await self.clear_roles(guild_id, target_discord_id)

        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            user_id = await UserRepo.ensure_exists(conn, discord_id=target_discord_id)

            await ModerationRoleBackupsRepo.upsert(conn, guild_id, user_id, roles)
            return True

    async def get_roles(
        self,
        guild_id: int,
        target_discord_id: int,
    ) -> Optional[List[int]]:
        """Récupère les rôles sauvegardés pour un utilisateur."""
        async with self._db.acquire() as conn:
            user_row = await UserRepo.get_by_discord_id(conn, target_discord_id)
            if not user_row:
                return None

            backup = await ModerationRoleBackupsRepo.get(
                conn, guild_id, user_row.user_id
            )
            if not backup:
                return None

            return backup.roles

    async def clear_roles(
        self,
        guild_id: int,
        target_discord_id: int,
    ) -> bool:
        """Supprime le backup des rôles. Retourne True si supprimé."""
        async with self._db.transaction() as conn:
            user_row = await UserRepo.get_by_discord_id(conn, target_discord_id)
            if not user_row:
                return False

            return await ModerationRoleBackupsRepo.delete(
                conn, guild_id, user_row.user_id
            )
