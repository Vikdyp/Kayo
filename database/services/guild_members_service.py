# database/services/guild_members_service.py
"""
Service DB pour les opérations sur les membres de guild.
Orchestration multi-repos (users + guild_members).
"""

import logging
from typing import Optional

from database.repos.user_repo import UserRepo
from database.repos.guild_member_repo import GuildMemberRepo
from database.repos.guilds_repo import GuildsRepo

logger = logging.getLogger(__name__)


class GuildMembersService:
    """
    Service DB pour les guild_members.
    Gère le mapping discord_id → user_id et les opérations membres.
    """

    def __init__(self, db):
        self._db = db

    async def has_accepted_rules(self, guild_id: int, discord_id: int) -> bool:
        """Vérifie si un membre a accepté les règles."""
        async with self._db.acquire() as conn:
            user_id = await UserRepo.get_user_id(conn, discord_id)
            if user_id is None:
                return False
            return await GuildMemberRepo.has_accepted_rules(
                conn, guild_id=guild_id, user_id=user_id
            )

    async def accept_rules(
        self, guild_id: int, guild_name: str, discord_id: int
    ) -> bool:
        """
        Enregistre qu'un membre a accepté les règles.
        Crée le user et le guild_member si nécessaire.
        """
        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            user_id = await UserRepo.ensure_exists(conn, discord_id=discord_id)
            await GuildMemberRepo.mark_join(
                conn, guild_id=guild_id, user_id=user_id
            )
            await GuildMemberRepo.mark_rules_accepted(
                conn, guild_id=guild_id, user_id=user_id
            )
        return True
