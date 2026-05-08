from cogs.admin.presenters import DEFAULT_ACTIVITY, format_status_update_message


def test_format_status_update_message_uses_default_activity() -> None:
    assert format_status_update_message("online", None) == (
        f"Status modifié à **online** et l'activité est maintenant **{DEFAULT_ACTIVITY}**."
    )


def test_format_status_update_message_uses_custom_activity() -> None:
    assert format_status_update_message("idle", "Maintenance") == (
        "Status modifié à **idle** et l'activité est maintenant **Maintenance**."
    )
