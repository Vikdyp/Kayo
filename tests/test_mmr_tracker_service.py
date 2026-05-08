from __future__ import annotations

import pytest
from datetime import datetime, timezone
from types import SimpleNamespace

from cogs.ranking.services.mmr_tracker_service import MmrTrackerService


class FakeValorantDb:
    def __init__(self):
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.last_history_row = None
        self.latest_partition = (8, 2)

    async def get_last_history_row(self, user_id: int):
        return self.last_history_row

    async def get_latest_partition(self):
        return self.latest_partition

    async def ensure_partitions(self, season: int, act: int) -> None:
        self.calls.append(("ensure_partitions", (season, act)))

    async def insert_history_entry(
        self,
        user_id: int,
        season: int,
        act: int,
        recorded_at,
        elo: int,
        is_win: bool,
    ) -> None:
        self.calls.append(
            ("insert_history_entry", (user_id, season, act, recorded_at, elo, is_win))
        )


@pytest.mark.asyncio
async def test_insert_history_entry_parses_episode_act_and_inserts():
    db = FakeValorantDb()
    service = MmrTrackerService(db, object())
    recorded_at = datetime(2026, 5, 8, tzinfo=timezone.utc)

    await service.insert_history_entry(
        10,
        {"date": recorded_at, "season": {"short": "e8a2"}, "elo": 542, "rr": 19},
    )

    assert db.calls == [
        ("ensure_partitions", (8, 2)),
        ("insert_history_entry", (10, 8, 2, recorded_at, 542, True)),
    ]


@pytest.mark.asyncio
async def test_insert_history_entry_ignores_invalid_season():
    db = FakeValorantDb()
    service = MmrTrackerService(db, object())

    await service.insert_history_entry(
        10,
        {"date": datetime.now(timezone.utc), "season": {"short": "episode-8-act-2"}, "elo": 542, "rr": 19},
    )

    assert db.calls == []


@pytest.mark.asyncio
async def test_record_current_mmr_snapshot_inserts_when_elo_changed():
    db = FakeValorantDb()
    db.last_history_row = SimpleNamespace(elo=520)
    service = MmrTrackerService(db, object())

    inserted = await service.record_current_mmr_snapshot(
        {"user_id": 10, "elo": 542, "current_season": 8, "current_act": 2},
    )

    assert inserted is True
    assert db.calls[0] == ("ensure_partitions", (8, 2))
    assert db.calls[1][0] == "insert_history_entry"
    user_id, season, act, recorded_at, elo, is_win = db.calls[1][1]
    assert (user_id, season, act, elo, is_win) == (10, 8, 2, 542, True)
    assert recorded_at.tzinfo is not None


@pytest.mark.asyncio
async def test_record_current_mmr_snapshot_skips_unchanged_elo():
    db = FakeValorantDb()
    db.last_history_row = SimpleNamespace(elo=542)
    service = MmrTrackerService(db, object())

    inserted = await service.record_current_mmr_snapshot(
        {"user_id": 10, "elo": 542, "current_season": 8, "current_act": 2},
    )

    assert inserted is False
    assert db.calls == []
