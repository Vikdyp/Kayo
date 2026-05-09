from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from database.repos.guild_member_repo import GuildMemberRepo
from database.repos.guilds_repo import GuildsRepo
from database.repos.user_repo import UserRepo


@dataclass(frozen=True, slots=True)
class RulesAcceptanceResult:
    accepted: bool
    already_accepted: bool


class GuildMembersService:
    """DB service for per-guild member state."""

    def __init__(self, db):
        self._db = db

    async def ensure_member(
        self,
        *,
        guild_id: int,
        guild_name: Optional[str],
        discord_user_id: int,
    ) -> int:
        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            user_id = await UserRepo.ensure_exists(conn, discord_id=discord_user_id)
            await GuildMemberRepo.mark_join(conn, guild_id=guild_id, user_id=user_id)
            return user_id

    async def has_accepted_rules(self, *, guild_id: int, discord_user_id: int) -> bool:
        async with self._db.acquire() as conn:
            user_id = await UserRepo.get_user_id(conn, discord_user_id)
            if user_id is None:
                return False
            return await GuildMemberRepo.has_accepted_rules(
                conn,
                guild_id=guild_id,
                user_id=user_id,
            )

    async def accept_rules(
        self,
        *,
        guild_id: int,
        guild_name: Optional[str],
        discord_user_id: int,
    ) -> RulesAcceptanceResult:
        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            user_id = await UserRepo.ensure_exists(conn, discord_id=discord_user_id)
            await GuildMemberRepo.mark_join(conn, guild_id=guild_id, user_id=user_id)

            already_accepted = await GuildMemberRepo.has_accepted_rules(
                conn,
                guild_id=guild_id,
                user_id=user_id,
            )
            if already_accepted:
                return RulesAcceptanceResult(accepted=False, already_accepted=True)

            await GuildMemberRepo.mark_rules_accepted(
                conn,
                guild_id=guild_id,
                user_id=user_id,
            )
            return RulesAcceptanceResult(accepted=True, already_accepted=False)
