from __future__ import annotations

from dataclasses import dataclass

from cogs.admin.presenters import build_permissions_csv


@dataclass(frozen=True)
class FakeRole:
    name: str
    position: int


class FakePermissions:
    def __init__(self, **values: bool) -> None:
        self.__dict__.update(values)


class FakeChannel:
    def __init__(self, name: str, channel_type: str, permissions_by_role: dict[str, FakePermissions]) -> None:
        self.name = name
        self.type = channel_type
        self._permissions_by_role = permissions_by_role

    def permissions_for(self, role: FakeRole) -> FakePermissions:
        return self._permissions_by_role.get(role.name, FakePermissions())


def test_build_permissions_csv_orders_roles_and_permissions() -> None:
    admin = FakeRole(name="Admin", position=10)
    member = FakeRole(name="Member", position=1)
    channel = FakeChannel(
        "general",
        "text",
        {
            "Admin": FakePermissions(view_channel=True, manage_messages=True),
            "Member": FakePermissions(view_channel=True, manage_messages=False),
        },
    )

    csv_content = build_permissions_csv(
        roles=[member, admin],
        channels=[channel],
        permissions=("view_channel", "manage_messages"),
    )

    assert csv_content.splitlines() == [
        "Salon : general [text]",
        "",
        "Permission,Admin,Member",
        "View Channel,yes,yes",
        "Manage Messages,yes,",
        "",
        "",
    ]
