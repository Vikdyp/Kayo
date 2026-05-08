# cogs/admin/presenters/status_messages.py
"""Status command messages."""

DEFAULT_ACTIVITY = "Perfect Team"


def format_status_update_message(status_value: str, activity: str | None) -> str:
    activity_label = activity or DEFAULT_ACTIVITY
    return (
        f"Status modifié à **{status_value}** et l'activité est maintenant "
        f"**{activity_label}**."
    )
