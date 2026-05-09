from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence
from typing import Protocol


PERMISSIONS_TO_REPORT = (
    "create_instant_invite",
    "kick_members",
    "ban_members",
    "administrator",
    "manage_channels",
    "manage_guild",
    "add_reactions",
    "view_audit_log",
    "priority_speaker",
    "stream",
    "view_channel",
    "send_messages",
    "send_tts_messages",
    "manage_messages",
    "embed_links",
    "attach_files",
    "read_message_history",
    "mention_everyone",
    "use_external_emojis",
    "connect",
    "speak",
    "mute_members",
    "deafen_members",
    "move_members",
    "use_vad",
    "manage_roles",
    "manage_webhooks",
    "manage_emojis",
)


class ReportRole(Protocol):
    name: str
    position: int


class ReportChannel(Protocol):
    name: str
    type: object

    def permissions_for(self, role: ReportRole) -> object:
        ...


def build_permissions_csv(
    *,
    roles: Iterable[ReportRole],
    channels: Iterable[ReportChannel],
    permissions: Sequence[str] = PERMISSIONS_TO_REPORT,
) -> str:
    sorted_roles = sorted(roles, key=lambda role: role.position, reverse=True)
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")

    for channel in channels:
        writer.writerow([f"Salon : {channel.name} [{channel.type}]"])
        writer.writerow([])
        writer.writerow(["Permission", *(role.name for role in sorted_roles)])

        for permission_name in permissions:
            writer.writerow(
                [
                    _format_permission_name(permission_name),
                    *[
                        "yes" if bool(getattr(channel.permissions_for(role), permission_name, False)) else ""
                        for role in sorted_roles
                    ],
                ]
            )

        writer.writerow([])
        writer.writerow([])

    return output.getvalue()


def _format_permission_name(permission_name: str) -> str:
    return permission_name.replace("_", " ").title()
