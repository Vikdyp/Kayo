from __future__ import annotations

import random
import re
import time
from collections.abc import Sequence

DEFAULT_QUOI_RESPONSES = ("feur !", "coubeh !", "de neuf ?", "de beau ?")
QUOI_TRIGGER_PATTERN = re.compile(r"\bquoi\s*[?!.,]*\s*$", re.IGNORECASE)


class QuoiResponderService:
    def __init__(
        self,
        *,
        responses: Sequence[str] = DEFAULT_QUOI_RESPONSES,
        max_responses_per_user: int = 5,
        time_window_seconds: float = 60.0,
    ) -> None:
        self._responses = tuple(responses)
        self._max_responses_per_user = max_responses_per_user
        self._time_window_seconds = time_window_seconds
        self._timestamps_by_user: dict[int, list[float]] = {}

    def matches_trigger(self, content: str) -> bool:
        return bool(QUOI_TRIGGER_PATTERN.search(content.strip()))

    def allow_response(self, user_id: int, *, now: float | None = None) -> bool:
        current_time = time.time() if now is None else now
        timestamps = [
            timestamp
            for timestamp in self._timestamps_by_user.get(user_id, [])
            if current_time - timestamp < self._time_window_seconds
        ]
        if len(timestamps) >= self._max_responses_per_user:
            self._timestamps_by_user[user_id] = timestamps
            return False

        timestamps.append(current_time)
        self._timestamps_by_user[user_id] = timestamps
        return True

    def build_response(self, emoji_text: str = ":pepe_clown:") -> str:
        return f"{random.choice(self._responses)} {emoji_text}"

    def clear(self) -> None:
        self._timestamps_by_user.clear()
