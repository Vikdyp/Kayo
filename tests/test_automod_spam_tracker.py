from datetime import datetime, timedelta

from cogs.moderation.services.automod_spam_tracker import AutomodSpamTracker


def test_spam_tracker_detects_same_content_across_channels() -> None:
    tracker = AutomodSpamTracker()
    now = datetime(2026, 5, 8, 12, 0)

    assert tracker.record_and_detect(
        user_id=1,
        guild_id=10,
        channel_id=100,
        message_id=1000,
        content=" Same message ",
        threshold=2,
        time_window_seconds=60,
        now=now,
    ) is False

    assert tracker.record_and_detect(
        user_id=1,
        guild_id=10,
        channel_id=101,
        message_id=1001,
        content="same message",
        threshold=2,
        time_window_seconds=60,
        now=now + timedelta(seconds=5),
    ) is True


def test_spam_tracker_ignores_old_messages_and_other_guilds() -> None:
    tracker = AutomodSpamTracker()
    now = datetime(2026, 5, 8, 12, 0)

    tracker.record_and_detect(
        user_id=1,
        guild_id=10,
        channel_id=100,
        message_id=1000,
        content="same",
        threshold=2,
        time_window_seconds=60,
        now=now,
    )

    assert tracker.record_and_detect(
        user_id=1,
        guild_id=11,
        channel_id=101,
        message_id=1001,
        content="same",
        threshold=2,
        time_window_seconds=60,
        now=now + timedelta(seconds=5),
    ) is False

    assert tracker.record_and_detect(
        user_id=1,
        guild_id=10,
        channel_id=102,
        message_id=1002,
        content="same",
        threshold=2,
        time_window_seconds=60,
        now=now + timedelta(seconds=61),
    ) is False


def test_spam_tracker_message_refs_match_recent_content() -> None:
    tracker = AutomodSpamTracker()
    now = datetime(2026, 5, 8, 12, 0)

    tracker.record_and_detect(
        user_id=1,
        guild_id=10,
        channel_id=100,
        message_id=1000,
        content="same",
        threshold=2,
        time_window_seconds=60,
        now=now,
    )
    tracker.record_and_detect(
        user_id=1,
        guild_id=10,
        channel_id=101,
        message_id=1001,
        content="same",
        threshold=2,
        time_window_seconds=60,
        now=now + timedelta(seconds=1),
    )

    refs = tracker.get_matching_message_refs(
        user_id=1,
        guild_id=10,
        content=" same ",
        now=now + timedelta(seconds=2),
    )

    assert refs == [(100, 1000), (101, 1001)]


def test_spam_tracker_honors_configured_detection_window() -> None:
    tracker = AutomodSpamTracker()
    now = datetime(2026, 5, 8, 12, 0)

    tracker.record_and_detect(
        user_id=1,
        guild_id=10,
        channel_id=100,
        message_id=1000,
        content="same",
        threshold=2,
        time_window_seconds=300,
        now=now,
    )

    assert tracker.record_and_detect(
        user_id=1,
        guild_id=10,
        channel_id=101,
        message_id=1001,
        content="same",
        threshold=2,
        time_window_seconds=300,
        now=now + timedelta(seconds=180),
    ) is True


def test_spam_tracker_flags_pending_spam_content_and_expires() -> None:
    tracker = AutomodSpamTracker()
    now = datetime(2026, 5, 8, 12, 0)

    tracker.flag_pending_spam(
        user_id=1,
        guild_id=10,
        content="Same spam",
        now=now,
        duration=timedelta(seconds=30),
    )

    assert tracker.is_pending_spam_message(
        user_id=1,
        guild_id=10,
        content=" same spam ",
        now=now + timedelta(seconds=10),
    ) is True
    assert tracker.is_pending_spam_message(
        user_id=1,
        guild_id=10,
        content="different",
        now=now + timedelta(seconds=10),
    ) is False
    assert tracker.is_pending_spam_message(
        user_id=1,
        guild_id=10,
        content="same spam",
        now=now + timedelta(seconds=31),
    ) is False
    assert tracker.pending_spam_content == {}


def test_spam_tracker_whitelist_expires() -> None:
    tracker = AutomodSpamTracker()
    now = datetime(2026, 5, 8, 12, 0)

    tracker.add_to_whitelist(1, 10, now=now, duration=timedelta(seconds=5))

    assert tracker.is_whitelisted(1, 10, now=now + timedelta(seconds=4)) is True
    assert tracker.is_whitelisted(1, 10, now=now + timedelta(seconds=6)) is False
    assert tracker.spam_whitelist == {}
