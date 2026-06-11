from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from cogs.ranking.services.mmr_tracker_service import MmrTrackerService
from integrations.exceptions import ApiError, RateLimitError


def ns(**kwargs):
    return SimpleNamespace(**kwargs)


class FakeValorantDb:
    def __init__(self):
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.last_history_row = None
        self.info = None
        self.latest_partition = None
        self.backfill_attempts: list[tuple[int, str | None]] = []
        self.backfilled: list[int] = []

    async def get_last_history_row(self, user_id: int, puuid: str | None = None):
        self.calls.append(("get_last_history_row", (user_id, puuid)))
        return self.last_history_row

    async def get_latest_partition(self):
        self.calls.append(("get_latest_partition", ()))
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
        *,
        puuid: str | None = None,
        rr_delta: int | None = None,
        match_id: str | None = None,
        source: str = "tracker_snapshot",
    ) -> bool:
        self.calls.append(
            (
                "insert_history_entry",
                (user_id, season, act, recorded_at, elo, is_win, puuid, rr_delta, match_id, source),
            )
        )
        return True

    async def get_valorant_info_by_discord_id(self, discord_id: int):
        self.calls.append(("get_valorant_info_by_discord_id", (discord_id,)))
        return self.info

    async def mark_mmr_history_backfill_attempt(
        self, user_id: int, error: str | None = None
    ) -> None:
        self.backfill_attempts.append((user_id, error))

    async def mark_mmr_history_backfilled(self, user_id: int) -> None:
        self.backfilled.append(user_id)


class FakeHenrik:
    def __init__(
        self,
        *,
        stored=None,
        stored_pages=None,
        live=None,
        stored_error=None,
        live_error=None,
    ):
        self.stored = stored
        self.stored_pages = stored_pages
        self.live = live
        self.stored_error = stored_error
        self.live_error = live_error
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    async def get_stored_mmr_history_by_puuid(
        self,
        region: str,
        platform: str,
        puuid: str,
        *,
        page=None,
        size=None,
    ):
        self.calls.append(("stored", (region, platform, puuid, page, size)))
        if self.stored_error:
            raise self.stored_error
        if self.stored_pages is not None:
            return self.stored_pages[page], None
        return self.stored, None

    async def get_mmr_history_by_puuid(self, region: str, platform: str, puuid: str):
        self.calls.append(("live", (region, platform, puuid)))
        if self.live_error:
            raise self.live_error
        return self.live, None


def player_info(**overrides):
    values = {
        "user_id": 10,
        "puuid": "puuid-1",
        "region": "eu",
        "platform": "pc",
        "mmr_history_backfilled_at": None,
    }
    values.update(overrides)
    return ns(**values)


def history_entry(**overrides):
    values = {
        "date": datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc),
        "season": ns(short="e8a2"),
        "elo": 542,
        "rr": 99,
        "last_change": -16,
        "match_id": "match-1",
    }
    values.update(overrides)
    return ns(**values)


def stored_response(entries, *, total=None, returned=None, before=0, after=0):
    if total is None:
        total = len(entries)
    if returned is None:
        returned = len(entries)
    return ns(
        status=200,
        data=entries,
        results=ns(total=total, returned=returned, before=before, after=after),
    )


@pytest.mark.asyncio
async def test_insert_history_entry_stores_metadata_and_uses_delta_for_is_win():
    db = FakeValorantDb()
    service = MmrTrackerService(db, object())
    recorded_at = datetime(2026, 5, 8, tzinfo=timezone.utc)

    inserted = await service.insert_history_entry(
        10,
        {
            "date": recorded_at,
            "season": {"short": "e8a2"},
            "elo": 542,
            "rr": 99,
            "rr_delta": -16,
            "match_id": "match-1",
        },
        puuid="puuid-1",
        source="henrik_live",
    )

    assert inserted is True
    assert db.calls == [
        ("ensure_partitions", (8, 2)),
        (
            "insert_history_entry",
            (10, 8, 2, recorded_at, 542, False, "puuid-1", -16, "match-1", "henrik_live"),
        ),
    ]


@pytest.mark.asyncio
async def test_insert_history_entry_ignores_invalid_season():
    db = FakeValorantDb()
    service = MmrTrackerService(db, object())

    inserted = await service.insert_history_entry(
        10,
        {"date": datetime.now(timezone.utc), "season": {"short": "episode-8-act-2"}, "elo": 542, "rr": 19},
    )

    assert inserted is False
    assert db.calls == []


@pytest.mark.asyncio
async def test_record_current_mmr_snapshot_inserts_when_elo_changed_for_current_puuid():
    db = FakeValorantDb()
    db.last_history_row = ns(elo=520)
    service = MmrTrackerService(db, object())

    inserted = await service.record_current_mmr_snapshot(
        {
            "user_id": 10,
            "puuid": "puuid-1",
            "region": "eu",
            "platform": "pc",
            "elo": 542,
            "current_season": 8,
            "current_act": 2,
            "mmr_history_backfilled_at": datetime.now(timezone.utc),
        },
    )

    assert inserted is True
    assert db.calls[0] == ("get_last_history_row", (10, "puuid-1"))
    assert db.calls[1] == ("ensure_partitions", (8, 2))
    assert db.calls[2][0] == "insert_history_entry"
    user_id, season, act, recorded_at, elo, is_win, puuid, rr_delta, match_id, source = db.calls[2][1]
    assert (user_id, season, act, elo, is_win, puuid, rr_delta, match_id, source) == (
        10,
        8,
        2,
        542,
        True,
        "puuid-1",
        22,
        None,
        "tracker_snapshot",
    )
    assert recorded_at.tzinfo is not None


@pytest.mark.asyncio
async def test_record_current_mmr_snapshot_skips_unchanged_elo():
    db = FakeValorantDb()
    db.last_history_row = ns(elo=542)
    service = MmrTrackerService(db, object())

    inserted = await service.record_current_mmr_snapshot(
        {
            "user_id": 10,
            "puuid": "puuid-1",
            "region": "eu",
            "platform": "pc",
            "elo": 542,
            "current_season": 8,
            "current_act": 2,
            "mmr_history_backfilled_at": datetime.now(timezone.utc),
        },
    )

    assert inserted is False
    assert db.calls == [("get_last_history_row", (10, "puuid-1"))]


@pytest.mark.asyncio
async def test_record_current_mmr_snapshot_falls_back_to_latest_partition():
    db = FakeValorantDb()
    db.latest_partition = (8, 2)
    db.last_history_row = ns(elo=520)
    service = MmrTrackerService(db, object())

    inserted = await service.record_current_mmr_snapshot(
        {
            "user_id": 10,
            "puuid": "puuid-1",
            "region": "eu",
            "platform": "pc",
            "elo": 542,
            "current_season": None,
            "current_act": None,
            "mmr_history_backfilled_at": datetime.now(timezone.utc),
        },
    )

    assert inserted is True
    assert db.calls[0] == ("get_latest_partition", ())
    assert db.calls[1] == ("get_last_history_row", (10, "puuid-1"))
    assert db.calls[2] == ("ensure_partitions", (8, 2))


@pytest.mark.asyncio
async def test_record_current_mmr_snapshot_skips_incomplete_account():
    db = FakeValorantDb()
    service = MmrTrackerService(db, object())

    inserted = await service.record_current_mmr_snapshot(
        {"user_id": 10, "elo": 542, "current_season": 8, "current_act": 2},
    )

    assert inserted is False
    assert db.calls == []


@pytest.mark.asyncio
async def test_fetch_full_history_imports_stored_history():
    db = FakeValorantDb()
    db.info = player_info()
    henrik = FakeHenrik(stored=ns(status=200, data=[history_entry()]))
    service = MmrTrackerService(db, henrik)

    result = await service.fetch_full_history(123)

    assert result.status == "imported"
    assert result.inserted_count == 1
    assert result.source == "henrik_stored"
    assert henrik.calls == [("stored", ("eu", "pc", "puuid-1", None, None))]
    assert db.backfill_attempts == [(10, None)]
    assert db.backfilled == [10]
    assert db.calls[-1][1][-4:] == ("puuid-1", -16, "match-1", "henrik_stored")


@pytest.mark.asyncio
async def test_fetch_full_history_imports_all_stored_pages():
    db = FakeValorantDb()
    db.info = player_info()
    henrik = FakeHenrik(
        stored_pages={
            None: stored_response(
                [history_entry(match_id="match-1"), history_entry(match_id="match-2")],
                total=3,
                returned=2,
                before=0,
                after=1,
            ),
            2: stored_response(
                [history_entry(match_id="match-3")],
                total=3,
                returned=1,
                before=2,
                after=0,
            ),
        },
    )
    service = MmrTrackerService(db, henrik)

    result = await service.fetch_full_history(123)

    assert result.status == "imported"
    assert result.inserted_count == 3
    assert result.source == "henrik_stored"
    assert henrik.calls == [
        ("stored", ("eu", "pc", "puuid-1", None, None)),
        ("stored", ("eu", "pc", "puuid-1", 2, 2)),
    ]
    assert db.backfilled == [10]


@pytest.mark.asyncio
async def test_fetch_full_history_falls_back_to_live_history():
    db = FakeValorantDb()
    db.info = player_info()
    henrik = FakeHenrik(
        stored=ns(status=200, data=[]),
        live=ns(status=200, data=ns(history=[history_entry(match_id="live-1", last_change=24)])),
    )
    service = MmrTrackerService(db, henrik)

    result = await service.fetch_full_history(123)

    assert result.status == "imported"
    assert result.source == "henrik_live"
    assert henrik.calls == [
        ("stored", ("eu", "pc", "puuid-1", None, None)),
        ("live", ("eu", "pc", "puuid-1")),
    ]
    assert db.calls[-1][1][-4:] == ("puuid-1", 24, "live-1", "henrik_live")


@pytest.mark.asyncio
async def test_fetch_full_history_returns_pending_when_account_is_not_synced():
    db = FakeValorantDb()
    db.info = player_info(puuid=None)
    service = MmrTrackerService(db, FakeHenrik())

    result = await service.fetch_full_history(123)

    assert result.status == "pending_sync"
    assert db.backfill_attempts == []


@pytest.mark.asyncio
async def test_fetch_full_history_returns_empty_when_api_has_no_history():
    db = FakeValorantDb()
    db.info = player_info()
    service = MmrTrackerService(
        db,
        FakeHenrik(stored=ns(status=200, data=[]), live=ns(status=200, data=ns(history=[]))),
    )

    result = await service.fetch_full_history(123)

    assert result.status == "empty"
    assert db.backfill_attempts == [(10, None), (10, "empty")]
    assert db.backfilled == []


@pytest.mark.asyncio
async def test_fetch_full_history_returns_rate_limited():
    db = FakeValorantDb()
    db.info = player_info()
    service = MmrTrackerService(db, FakeHenrik(stored_error=RateLimitError("limited")))

    result = await service.fetch_full_history(123)

    assert result.status == "rate_limited"
    assert db.backfill_attempts == [(10, None), (10, "rate_limited")]
    assert db.backfilled == []


@pytest.mark.asyncio
async def test_fetch_full_history_falls_back_to_live_when_stored_is_missing():
    db = FakeValorantDb()
    db.info = player_info()
    service = MmrTrackerService(
        db,
        FakeHenrik(
            stored_error=ApiError("HTTP 404: not found"),
            live=ns(status=200, data=ns(history=[history_entry(match_id="live-1")])),
        ),
    )

    result = await service.fetch_full_history(123)

    assert result.status == "imported"
    assert result.source == "henrik_live"
    assert db.backfill_attempts == [(10, None)]
    assert db.backfilled == [10]


@pytest.mark.asyncio
async def test_fetch_full_history_returns_error_on_stored_failure_without_live_fallback():
    db = FakeValorantDb()
    db.info = player_info()
    service = MmrTrackerService(
        db,
        FakeHenrik(
            stored_error=RuntimeError("stored page failed"),
            live=ns(status=200, data=ns(history=[history_entry()])),
        ),
    )

    result = await service.fetch_full_history(123)

    assert result.status == "error"
    assert result.error == "stored page failed"
    assert db.backfill_attempts == [(10, None), (10, "stored page failed")]
    assert db.backfilled == []


@pytest.mark.asyncio
async def test_fetch_full_history_returns_error_on_live_failure():
    db = FakeValorantDb()
    db.info = player_info()
    service = MmrTrackerService(
        db,
        FakeHenrik(stored=ns(status=200, data=[]), live_error=RuntimeError("downstream failed")),
    )

    result = await service.fetch_full_history(123)

    assert result.status == "error"
    assert result.error == "downstream failed"
    assert db.backfill_attempts == [(10, None), (10, "downstream failed")]


@pytest.mark.asyncio
async def test_tracked_row_backfill_is_throttled_by_attempted_at():
    db = FakeValorantDb()
    service = MmrTrackerService(db, FakeHenrik())

    inserted = await service.record_current_mmr_snapshot(
        {
            "user_id": 10,
            "puuid": "puuid-1",
            "region": "eu",
            "platform": "pc",
            "elo": 542,
            "current_season": 8,
            "current_act": 2,
            "mmr_history_backfilled_at": None,
            "mmr_history_backfill_attempted_at": datetime.now(timezone.utc) - timedelta(minutes=5),
        },
    )

    assert inserted is True
    assert db.backfill_attempts == []
