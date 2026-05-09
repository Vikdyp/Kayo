from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Optional

import discord
from discord.ext import commands

from cogs.moderation.services.moderation_service import ModerationService

logger = logging.getLogger(__name__)


def collect_restorable_role_ids(
    member: discord.Member,
    *,
    ban_role_name: str = "ban",
) -> list[int]:
    return [
        role.id
        for role in member.roles
        if role != member.guild.default_role
        and role.name.casefold() != ban_role_name.casefold()
    ]


def can_bot_manage_role(guild: discord.Guild, role: discord.Role) -> bool:
    if role == guild.default_role or role.managed:
        return False

    bot_member = guild.me
    if bot_member is None:
        return True

    try:
        return role < bot_member.top_role
    except TypeError:
        return True


def filter_removable_roles(
    member: discord.Member,
    *,
    protected_roles: Iterable[discord.Role] = (),
) -> list[discord.Role]:
    protected_role_ids = {role.id for role in protected_roles}
    return [
        role
        for role in member.roles
        if role.id not in protected_role_ids
        and can_bot_manage_role(member.guild, role)
    ]


def filter_assignable_roles(
    guild: discord.Guild,
    roles: Iterable[Optional[discord.Role]],
) -> list[discord.Role]:
    return [
        role
        for role in roles
        if role is not None and can_bot_manage_role(guild, role)
    ]


async def apply_ban_role_all_guilds(
    bot: commands.Bot,
    moderation_service: ModerationService,
    user_id: int,
    reason: str,
    *,
    source_member: Optional[discord.Member] = None,
) -> None:
    for guild in bot.guilds:
        if source_member and guild.id == source_member.guild.id:
            member = source_member
        else:
            member = guild.get_member(user_id)

        if not member:
            logger.debug("Member %s not found in guild cache %s.", user_id, guild.name)
            continue

        ban_role_id = await moderation_service.get_ban_role_id(guild.id)
        if not ban_role_id:
            logger.debug("Ban role is not configured for guild %s.", guild.name)
            continue

        ban_role = guild.get_role(ban_role_id)
        if not ban_role:
            logger.warning("Configured ban role %s not found in guild %s.", ban_role_id, guild.name)
            continue
        has_ban_role = ban_role in member.roles
        if not has_ban_role and not can_bot_manage_role(guild, ban_role):
            logger.warning("Bot cannot manage ban role %s in guild %s.", ban_role.name, guild.name)
            continue

        try:
            roles_to_remove = filter_removable_roles(member, protected_roles=(ban_role,))
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason=reason)
                logger.info("Removed roles for %s in %s.", member.display_name, guild.name)

            if has_ban_role:
                logger.debug("Member %s already has ban role in guild %s.", member.display_name, guild.name)
                continue

            await member.add_roles(ban_role, reason=reason)
            logger.info("Applied ban role to %s in %s.", member.display_name, guild.name)

        except discord.Forbidden:
            logger.error("Missing permissions to apply ban role to %s in %s.", member.display_name, guild.name)
        except discord.HTTPException as exc:
            logger.error("HTTP error while applying ban role to %s in %s: %s", member.display_name, guild.name, exc)
