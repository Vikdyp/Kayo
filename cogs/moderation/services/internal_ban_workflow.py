from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import discord
from discord.ext import commands

from cogs.moderation.discord_actions import (
    apply_ban_role_all_guilds,
    collect_restorable_role_ids,
    filter_assignable_roles,
)
from cogs.moderation.services.moderation_service import ModerationService

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class InternalBanResult:
    roles_backed_up: tuple[int, ...]
    ban_end: Optional[datetime]
    ban_recorded: bool


@dataclass(frozen=True, slots=True)
class InternalBanEnforcementResult:
    ban_found: bool


@dataclass(frozen=True, slots=True)
class InternalUnbanResult:
    ban_found: bool
    saved_roles: tuple[int, ...]
    removed_ban_roles: int = 0
    restored_roles: int = 0
    ban_removed: bool = False
    backup_cleared: bool = False


async def apply_internal_ban(
    *,
    bot: commands.Bot,
    moderation_service: ModerationService,
    guild: discord.Guild,
    member: discord.Member,
    reason: str,
    banned_by_id: int,
    ban_type: str,
    ban_end: Optional[datetime],
    role_reason: Optional[str] = None,
) -> InternalBanResult:
    roles_to_backup = tuple(collect_restorable_role_ids(member))

    await moderation_service.update_roles_backup(
        guild_id=guild.id,
        guild_name=guild.name,
        discord_user_id=member.id,
        roles=list(roles_to_backup),
    )

    ban_recorded = await moderation_service.add_ban(
        guild_id=guild.id,
        guild_name=guild.name,
        user_id=member.id,
        ban_type=ban_type,
        reason=reason,
        banned_by=banned_by_id,
        ban_end=ban_end,
    )
    if not ban_recorded:
        return InternalBanResult(
            roles_backed_up=roles_to_backup,
            ban_end=ban_end,
            ban_recorded=False,
        )

    await apply_ban_role_all_guilds(
        bot,
        moderation_service,
        member.id,
        role_reason or reason,
        source_member=member,
    )

    return InternalBanResult(
        roles_backed_up=roles_to_backup,
        ban_end=ban_end,
        ban_recorded=True,
    )


async def enforce_existing_internal_ban(
    *,
    bot: commands.Bot,
    moderation_service: ModerationService,
    guild: discord.Guild,
    member: discord.Member,
    reason: Optional[str] = None,
) -> InternalBanEnforcementResult:
    ban_info = await moderation_service.get_ban_info(guild.id, member.id)
    if not ban_info:
        return InternalBanEnforcementResult(ban_found=False)

    await apply_ban_role_all_guilds(
        bot,
        moderation_service,
        member.id,
        reason or "Ban interne actif: reapplique automatiquement.",
        source_member=member,
    )
    return InternalBanEnforcementResult(ban_found=True)


async def remove_internal_ban(
    *,
    bot: commands.Bot,
    moderation_service: ModerationService,
    guild: discord.Guild,
    user_id: int,
    reason: Optional[str] = None,
) -> InternalUnbanResult:
    ban_info = await moderation_service.get_ban_info(guild.id, user_id)
    if not ban_info:
        return InternalUnbanResult(ban_found=False, saved_roles=())

    saved_roles = tuple(await moderation_service.get_roles_backup(guild.id, user_id))
    removed_ban_roles = 0
    restored_roles = 0

    for target_guild in bot.guilds:
        member = target_guild.get_member(user_id)
        if not member:
            continue

        ban_role_id = await moderation_service.get_ban_role_id(target_guild.id)
        if ban_role_id:
            ban_role = target_guild.get_role(ban_role_id)
            if ban_role and ban_role in member.roles:
                try:
                    await member.remove_roles(
                        ban_role,
                        reason=f"Fin de ban: {reason or 'Debannissement'}",
                    )
                    removed_ban_roles += 1
                    logger.info("Removed ban role from %s in %s.", member.display_name, target_guild.name)
                except discord.Forbidden:
                    logger.error("Missing permissions to remove ban role from %s in %s.", member.display_name, target_guild.name)
                except discord.HTTPException as exc:
                    logger.error("HTTP error while removing ban role from %s in %s: %s", member.display_name, target_guild.name, exc)

        if target_guild.id == guild.id and saved_roles:
            roles_to_add = [
                discord.utils.get(target_guild.roles, id=role_id)
                for role_id in saved_roles
            ]
            roles_to_add = filter_assignable_roles(target_guild, roles_to_add)
            if roles_to_add:
                try:
                    await member.add_roles(
                        *roles_to_add,
                        reason="Restauration des roles apres debannissement.",
                    )
                    restored_roles += len(roles_to_add)
                    logger.info(
                        "Restored roles for %s in %s: %s",
                        member.display_name,
                        target_guild.name,
                        [role.name for role in roles_to_add],
                    )
                except discord.Forbidden:
                    logger.error("Missing permissions to restore roles for %s in %s.", member.display_name, target_guild.name)
                except discord.HTTPException as exc:
                    logger.exception("HTTP error while restoring roles for %s in %s: %s", member.display_name, target_guild.name, exc)

    ban_removed = await moderation_service.remove_ban(guild.id, user_id)
    backup_cleared = await moderation_service.clear_roles_backup(guild.id, user_id)

    return InternalUnbanResult(
        ban_found=True,
        saved_roles=saved_roles,
        removed_ban_roles=removed_ban_roles,
        restored_roles=restored_roles,
        ban_removed=ban_removed,
        backup_cleared=backup_cleared,
    )
