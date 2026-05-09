from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from cogs.moderation.services.internal_ban_workflow import (
    apply_internal_ban,
    enforce_existing_internal_ban,
    remove_internal_ban,
)


@dataclass
class FakeRole:
    id: int
    name: str
    position: int
    managed: bool = False

    def __lt__(self, other: "FakeRole") -> bool:
        return self.position < other.position


class FakeGuild:
    def __init__(self) -> None:
        self.id = 10
        self.name = "Perfect Team"
        self.default_role = FakeRole(1, "@everyone", 0)
        self.member_role = FakeRole(2, "Member", 10)
        self.ban_role = FakeRole(3, "ban", 20)
        self.me = SimpleNamespace(top_role=FakeRole(999, "Kayo", 50))
        self.roles = [self.default_role, self.member_role, self.ban_role]
        self._members: dict[int, FakeMember] = {}

    def add_member(self, member: "FakeMember") -> None:
        self._members[member.id] = member

    def get_member(self, user_id: int):
        return self._members.get(user_id)

    def get_role(self, role_id: int):
        return next((role for role in self.roles if role.id == role_id), None)


class FakeMember:
    def __init__(self, guild: FakeGuild, *, roles: list[FakeRole]) -> None:
        self.id = 42
        self.guild = guild
        self.roles = [guild.default_role, *roles]
        self.display_name = "Target"
        self.removed_roles: list[FakeRole] = []
        self.added_roles: list[FakeRole] = []

    async def remove_roles(self, *roles: FakeRole, reason: str | None = None) -> None:
        self.removed_roles.extend(roles)
        self.roles = [role for role in self.roles if role not in roles]

    async def add_roles(self, *roles: FakeRole, reason: str | None = None) -> None:
        self.added_roles.extend(roles)
        for role in roles:
            if role not in self.roles:
                self.roles.append(role)


class FakeModerationService:
    def __init__(self, guild: FakeGuild) -> None:
        self.guild = guild
        self.roles_backup: list[int] | None = None
        self.add_ban_kwargs: dict | None = None
        self.removed_ban: tuple[int, int] | None = None
        self.cleared_backup: tuple[int, int] | None = None
        self.ban_exists = True
        self.saved_roles = [guild.member_role.id]

    async def update_roles_backup(self, *, guild_id, guild_name, discord_user_id, roles):
        self.roles_backup = roles
        return True

    async def add_ban(self, **kwargs):
        self.add_ban_kwargs = kwargs
        return True

    async def get_ban_role_id(self, guild_id: int):
        return self.guild.ban_role.id

    async def get_ban_info(self, guild_id: int, user_id: int):
        return object() if self.ban_exists else None

    async def get_roles_backup(self, guild_id: int, user_id: int):
        return self.saved_roles

    async def remove_ban(self, guild_id: int, user_id: int):
        self.removed_ban = (guild_id, user_id)
        return True

    async def clear_roles_backup(self, guild_id: int, user_id: int):
        self.cleared_backup = (guild_id, user_id)
        return True


@pytest.mark.asyncio
async def test_apply_internal_ban_records_backup_and_adds_ban_role() -> None:
    guild = FakeGuild()
    member = FakeMember(guild, roles=[guild.member_role])
    guild.add_member(member)
    service = FakeModerationService(guild)
    bot = SimpleNamespace(guilds=[guild])

    result = await apply_internal_ban(
        bot=bot,
        moderation_service=service,
        guild=guild,
        member=member,
        reason="reason",
        banned_by_id=99,
        ban_type="perm",
        ban_end=None,
    )

    assert result.ban_recorded is True
    assert result.roles_backed_up == (guild.member_role.id,)
    assert service.roles_backup == [guild.member_role.id]
    assert service.add_ban_kwargs["banned_by"] == 99
    assert member.removed_roles == [guild.member_role]
    assert member.added_roles == [guild.ban_role]


@pytest.mark.asyncio
async def test_enforce_existing_internal_ban_does_not_overwrite_backup() -> None:
    guild = FakeGuild()
    member = FakeMember(guild, roles=[guild.member_role])
    guild.add_member(member)
    service = FakeModerationService(guild)
    bot = SimpleNamespace(guilds=[guild])

    result = await enforce_existing_internal_ban(
        bot=bot,
        moderation_service=service,
        guild=guild,
        member=member,
        reason="return",
    )

    assert result.ban_found is True
    assert service.roles_backup is None
    assert service.add_ban_kwargs is None
    assert member.removed_roles == [guild.member_role]
    assert member.added_roles == [guild.ban_role]


@pytest.mark.asyncio
async def test_enforce_existing_internal_ban_cleans_roles_when_ban_role_already_present() -> None:
    guild = FakeGuild()
    member = FakeMember(guild, roles=[guild.member_role, guild.ban_role])
    guild.add_member(member)
    service = FakeModerationService(guild)
    bot = SimpleNamespace(guilds=[guild])

    result = await enforce_existing_internal_ban(
        bot=bot,
        moderation_service=service,
        guild=guild,
        member=member,
        reason="role update",
    )

    assert result.ban_found is True
    assert member.removed_roles == [guild.member_role]
    assert member.added_roles == []


@pytest.mark.asyncio
async def test_remove_internal_ban_removes_ban_role_and_restores_saved_roles() -> None:
    guild = FakeGuild()
    member = FakeMember(guild, roles=[guild.ban_role])
    guild.add_member(member)
    service = FakeModerationService(guild)
    bot = SimpleNamespace(guilds=[guild])

    result = await remove_internal_ban(
        bot=bot,
        moderation_service=service,
        guild=guild,
        user_id=member.id,
        reason="done",
    )

    assert result.ban_found is True
    assert result.removed_ban_roles == 1
    assert result.restored_roles == 1
    assert service.removed_ban == (guild.id, member.id)
    assert service.cleared_backup == (guild.id, member.id)
    assert member.removed_roles == [guild.ban_role]
    assert member.added_roles == [guild.member_role]
