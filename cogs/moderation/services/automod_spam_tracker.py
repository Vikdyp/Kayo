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


@dataclass(frozen=True)
class PendingSpamContent:
    guild_id: int
    content_hash: int
    expires_at: datetime


class AutomodSpamTracker:
    def __init__(self) -> None:
        self.message_cache: dict[int, list[SpamMessageRecord]] = {}
        self.spam_whitelist: dict[tuple[int, int], datetime] = {}
        self.pending_spam_content: dict[tuple[int, int], PendingSpamContent] = {}

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
        self.cleanup(now=timestamp, max_age=timedelta(seconds=max(time_window_seconds, 120)))

        content_hash = self._content_hash(content)
        self.record_message(
            user_id=user_id,
            guild_id=guild_id,
            channel_id=channel_id,
            message_id=message_id,
            content=content,
            now=timestamp,
        )
        records = self.message_cache[user_id]

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

    def record_message(
        self,
        *,
        user_id: int,
        guild_id: int,
        channel_id: int,
        message_id: int,
        content: str,
        now: datetime | None = None,
    ) -> None:
        timestamp = now or datetime.utcnow()
        records = self.message_cache.setdefault(user_id, [])
        records.append(
            SpamMessageRecord(
                guild_id=guild_id,
                channel_id=channel_id,
                message_id=message_id,
                content_hash=self._content_hash(content),
                created_at=timestamp,
            )
        )

    def flag_pending_spam(
        self,
        *,
        user_id: int,
        guild_id: int,
        content: str,
        now: datetime | None = None,
        duration: timedelta = timedelta(minutes=5),
    ) -> datetime:
        timestamp = now or datetime.utcnow()
        expires_at = timestamp + duration
        self.pending_spam_content[(user_id, guild_id)] = PendingSpamContent(
            guild_id=guild_id,
            content_hash=self._content_hash(content),
            expires_at=expires_at,
        )
        return expires_at

    def is_pending_spam_message(
        self,
        *,
        user_id: int,
        guild_id: int,
        content: str,
        now: datetime | None = None,
    ) -> bool:
        key = (user_id, guild_id)
        pending = self.pending_spam_content.get(key)
        if pending is None:
            return False

        timestamp = now or datetime.utcnow()
        if timestamp >= pending.expires_at:
            del self.pending_spam_content[key]
            return False

        return pending.content_hash == self._content_hash(content)

    def clear_pending_spam(self, *, user_id: int, guild_id: int) -> None:
        self.pending_spam_content.pop((user_id, guild_id), None)

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
        timestamp = now or datetime.utcnow()
        cutoff = timestamp - max_age
        for user_id in list(self.message_cache.keys()):
            self.message_cache[user_id] = [
                record
                for record in self.message_cache[user_id]
                if record.created_at > cutoff
            ]
            if not self.message_cache[user_id]:
                del self.message_cache[user_id]
        for key, pending in list(self.pending_spam_content.items()):
            if timestamp >= pending.expires_at:
                del self.pending_spam_content[key]

    @staticmethod
    def _content_hash(content: str) -> int:
        return hash(content.lower().strip())
