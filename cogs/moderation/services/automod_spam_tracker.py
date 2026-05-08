# cogs/moderation/services/automod_spam_tracker.py
"""In-memory tracking for cross-channel spam detection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class SpamMessageRecord:
    guild_id: int
    channel_id: int
    message_id: int
    content_hash: int
    created_at: datetime


class AutomodSpamTracker:
    def __init__(self) -> None:
        self.message_cache: dict[int, list[SpamMessageRecord]] = {}
        self.spam_whitelist: dict[tuple[int, int], datetime] = {}

    def add_to_whitelist(
        self,
        user_id: int,
        guild_id: int,
        *,
        now: datetime | None = None,
        duration: timedelta = timedelta(hours=24),
    ) -> datetime:
        expires_at = (now or datetime.utcnow()) + duration
        self.spam_whitelist[(user_id, guild_id)] = expires_at
        return expires_at

    def is_whitelisted(
        self,
        user_id: int,
        guild_id: int,
        *,
        now: datetime | None = None,
    ) -> bool:
        key = (user_id, guild_id)
        expires_at = self.spam_whitelist.get(key)
        if not expires_at:
            return False

        if (now or datetime.utcnow()) < expires_at:
            return True

        del self.spam_whitelist[key]
        return False

    def record_and_detect(
        self,
        *,
        user_id: int,
        guild_id: int,
        channel_id: int,
        message_id: int,
        content: str,
        threshold: int,
        time_window_seconds: int,
        now: datetime | None = None,
    ) -> bool:
        timestamp = now or datetime.utcnow()
        self.cleanup(now=timestamp)

        records = self.message_cache.setdefault(user_id, [])
        content_hash = self._content_hash(content)
        records.append(
            SpamMessageRecord(
                guild_id=guild_id,
                channel_id=channel_id,
                message_id=message_id,
                content_hash=content_hash,
                created_at=timestamp,
            )
        )

        cutoff = timestamp - timedelta(seconds=time_window_seconds)
        recent_records = [
            record
            for record in records
            if record.created_at > cutoff and record.guild_id == guild_id
        ]
        channels_with_same_content = {
            record.channel_id
            for record in recent_records
            if record.content_hash == content_hash
        }

        return len(channels_with_same_content) >= threshold

    def get_matching_message_refs(
        self,
        *,
        user_id: int,
        guild_id: int,
        content: str,
        now: datetime | None = None,
        window_seconds: int = 60,
    ) -> list[tuple[int, int]]:
        timestamp = now or datetime.utcnow()
        cutoff = timestamp - timedelta(seconds=window_seconds)
        content_hash = self._content_hash(content)

        return [
            (record.channel_id, record.message_id)
            for record in self.message_cache.get(user_id, [])
            if (
                record.content_hash == content_hash
                and record.created_at > cutoff
                and record.guild_id == guild_id
            )
        ]

    def cleanup(
        self,
        *,
        now: datetime | None = None,
        max_age: timedelta = timedelta(minutes=2),
    ) -> None:
        cutoff = (now or datetime.utcnow()) - max_age
        for user_id in list(self.message_cache.keys()):
            self.message_cache[user_id] = [
                record
                for record in self.message_cache[user_id]
                if record.created_at > cutoff
            ]
            if not self.message_cache[user_id]:
                del self.message_cache[user_id]

    @staticmethod
    def _content_hash(content: str) -> int:
        return hash(content.lower().strip())
