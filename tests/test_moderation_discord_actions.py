from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from cogs.moderation.discord_actions import (
    collect_restorable_role_ids,
    filter_assignable_roles,
    filter_removable_roles,
)


@dataclass
class FakeRole:
    id: int
    name: str
    position: int
    managed: bool = False

    def __lt__(self, other: "FakeRole") -> bool:
        return self.position < other.position


def make_member(*roles: FakeRole):
    default_role = FakeRole(1, "@everyone", 0)
    top_role = FakeRole(999, "Kayo", 50)
    guild = SimpleNamespace(default_role=default_role, me=SimpleNamespace(top_role=top_role))
    member = SimpleNamespace(guild=guild, roles=[default_role, *roles])
    return guild, member


def test_collect_restorable_role_ids_excludes_default_and_ban_role():
    _, member = make_member(
        FakeRole(2, "Gold", 10),
        FakeRole(3, "BAN", 20),
        FakeRole(4, "Managed", 5, managed=True),
    )

    assert collect_restorable_role_ids(member) == [2, 4]


def test_filter_removable_roles_skips_protected_managed_and_higher_roles():
    ban_role = FakeRole(2, "ban", 10)
    managed_role = FakeRole(3, "Linked", 15, managed=True)
    regular_role = FakeRole(4, "Member", 20)
    higher_role = FakeRole(5, "Owner", 99)
    _, member = make_member(ban_role, managed_role, regular_role, higher_role)

    assert filter_removable_roles(member, protected_roles=(ban_role,)) == [regular_role]


def test_filter_assignable_roles_skips_none_default_managed_and_higher_roles():
    managed_role = FakeRole(3, "Linked", 15, managed=True)
    regular_role = FakeRole(4, "Member", 20)
    higher_role = FakeRole(5, "Owner", 99)
    guild, _ = make_member()

    roles = [None, guild.default_role, managed_role, regular_role, higher_role]

    assert filter_assignable_roles(guild, roles) == [regular_role]
