# cogs/moderation/presenters/clean_history.py
"""Display formatting for clean command history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable


@dataclass(frozen=True)
class DeletionHistoryEntry:
    id: int
    deleted_by_name: str
    channel_name: str
    deletion_type: str
    message_count: int
    created_at: datetime


DELETION_TYPE_ICONS = {
    "all": "🧹",
    "user": "👤",
    "links": "🔗",
    "image": "📷",
    "gif": "🎞️",
    "condition": "⚙️",
    "from": "➡️",
    "number": "🔢",
}


def get_deletion_type_icon(deletion_type: str) -> str:
    return DELETION_TYPE_ICONS.get(deletion_type, "❓")


def format_deletion_history_table(entries: Iterable[DeletionHistoryEntry]) -> str:
    table_header = (
        "╔════╦══════════════╦═════════════╦══════════════╦═══════╦══════════════════╗\n"
        "║ ID ║ Supprimé par ║ Salon       ║ Type         ║ Nb.   ║ Date             ║\n"
        "╠════╬══════════════╬═════════════╬══════════════╬═══════╬══════════════════╣\n"
    )

    rows = [
        (
            f"║ {entry.id:<2} ║ {entry.deleted_by_name:<12} ║ #{entry.channel_name:<10} ║ "
            f"{get_deletion_type_icon(entry.deletion_type)} {entry.deletion_type:<9} ║ "
            f"{entry.message_count:<5} ║ {entry.created_at.strftime('%d/%m/%Y %H:%M'):<15} ║"
        )
        for entry in entries
    ]

    table_footer = (
        "\n╚════╩══════════════╩═════════════╩══════════════╩═══════╩══════════════════╝"
    )

    return f"{table_header}{'\n'.join(rows)}{table_footer}"
