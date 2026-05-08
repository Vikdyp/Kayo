from datetime import datetime, timezone

from cogs.moderation.presenters import (
    DeletionHistoryEntry,
    format_deletion_history_table,
    get_deletion_type_icon,
)


def test_get_deletion_type_icon_returns_known_icon() -> None:
    assert get_deletion_type_icon("links") == "🔗"
    assert get_deletion_type_icon("unknown") == "❓"


def test_format_deletion_history_table_keeps_columns_and_values() -> None:
    history = format_deletion_history_table(
        [
            DeletionHistoryEntry(
                id=7,
                deleted_by_name="@Admin",
                channel_name="general",
                deletion_type="links",
                message_count=3,
                created_at=datetime(2026, 5, 8, 14, 30, tzinfo=timezone.utc),
            )
        ]
    )

    assert "Supprimé par" in history
    assert "@Admin" in history
    assert "#general" in history
    assert "🔗 links" in history
    assert "08/05/2026 14:30" in history
