from __future__ import annotations

import pytest

from database.repos.user_repo import UserRepo
from database.repos.valorant_elo_history_repo import ValorantEloHistoryRepo
from database.repos.valorant_info_repo import (
    ValorantInfoRow,
    ValorantInfoRepo,
    ValorantUserPresenceRow,
)
from database.services.valorant_db_service import ValorantDbService


class FakeTransaction:
    async def __aenter__(self):
        return "conn"

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeAcquire:
    async def __aenter__(self):
        return "conn"

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeDb:
    def transaction(self):
        return FakeTransaction()

    def acquire(self):
        return FakeAcquire()


@pytest.mark.asyncio
async def test_sync_presence_uses_repo_batch_methods(monkeypatch):
    calls: list[tuple[str, object]] = []

    async def get_user_ids_by_discord_ids(conn, discord_ids):
        calls.append(("lookup", (conn, set(discord_ids))))
        return [
            ValorantUserPresenceRow(user_id=1, discord_id=10),
            ValorantUserPresenceRow(user_id=2, discord_id=20),
            ValorantUserPresenceRow(user_id=3, discord_id=30),
        ]

    async def bulk_mark_active(conn, user_ids):
        calls.append(("active", (conn, user_ids)))
        return len(user_ids)

    async def bulk_mark_inactive(conn, user_ids):
        calls.append(("inactive", (conn, user_ids)))
        return len(user_ids)

    monkeypatch.setattr(
        ValorantInfoRepo,
        "get_user_ids_by_discord_ids",
        get_user_ids_by_discord_ids,
    )
    monkeypatch.setattr(ValorantInfoRepo, "bulk_mark_active", bulk_mark_active)
    monkeypatch.setattr(ValorantInfoRepo, "bulk_mark_inactive", bulk_mark_inactive)

    service = ValorantDbService(FakeDb())

    reactivated, deactivated = await service.sync_presence(
        active_discord_ids={10, 30},
        all_discord_ids={10, 20, 30},
    )

    assert (reactivated, deactivated) == (2, 1)
    assert calls == [
        ("lookup", ("conn", {10, 20, 30})),
        ("active", ("conn", [1, 3])),
        ("inactive", ("conn", [2])),
    ]


@pytest.mark.asyncio
async def test_get_history_reads_legacy_rows_while_puuid_is_pending(monkeypatch):
    calls: list[tuple[str, object]] = []

    async def get_user_id(conn, discord_id):
        calls.append(("get_user_id", (conn, discord_id)))
        return 10

    async def get_by_user_id(conn, user_id):
        calls.append(("get_by_user_id", (conn, user_id)))
        return ValorantInfoRow(
            user_id=user_id,
            pseudo="Player",
            tag="EUW",
            puuid=None,
            region=None,
            platform=None,
            rank=None,
            elo=None,
            current_season=None,
            current_act=None,
            is_active=True,
            tracking_enabled=True,
            error_count=0,
            last_error_at=None,
            last_checked_at=None,
            last_notification=None,
            deactivated_at=None,
            mmr_history_backfilled_at=None,
            mmr_history_backfill_attempted_at=None,
            mmr_history_backfill_error=None,
        )

    async def get_history(conn, user_id, season=None, act=None, puuid=None, legacy_only=False):
        calls.append(("get_history", (conn, user_id, season, act, puuid, legacy_only)))
        return ["legacy-row"]

    monkeypatch.setattr(UserRepo, "get_user_id", get_user_id)
    monkeypatch.setattr(ValorantInfoRepo, "get_by_user_id", get_by_user_id)
    monkeypatch.setattr(ValorantEloHistoryRepo, "get_history", get_history)

    service = ValorantDbService(FakeDb())

    rows = await service.get_history(123, season=8, act=2)

    assert rows == ["legacy-row"]
    assert calls[-1] == ("get_history", ("conn", 10, 8, 2, None, True))


@pytest.mark.asyncio
async def test_get_partitions_reads_legacy_rows_while_puuid_is_pending(monkeypatch):
    calls: list[tuple[str, object]] = []

    async def get_user_id(conn, discord_id):
        calls.append(("get_user_id", (conn, discord_id)))
        return 10

    async def get_by_user_id(conn, user_id):
        calls.append(("get_by_user_id", (conn, user_id)))
        return ValorantInfoRow(
            user_id=user_id,
            pseudo="Player",
            tag="EUW",
            puuid=None,
            region=None,
            platform=None,
            rank=None,
            elo=None,
            current_season=None,
            current_act=None,
            is_active=True,
            tracking_enabled=True,
            error_count=0,
            last_error_at=None,
            last_checked_at=None,
            last_notification=None,
            deactivated_at=None,
            mmr_history_backfilled_at=None,
            mmr_history_backfill_attempted_at=None,
            mmr_history_backfill_error=None,
        )

    async def get_distinct_partitions(conn, user_id, puuid=None, legacy_only=False):
        calls.append(("get_partitions", (conn, user_id, puuid, legacy_only)))
        return [(8, 2)]

    monkeypatch.setattr(UserRepo, "get_user_id", get_user_id)
    monkeypatch.setattr(ValorantInfoRepo, "get_by_user_id", get_by_user_id)
    monkeypatch.setattr(
        ValorantEloHistoryRepo,
        "get_distinct_partitions",
        get_distinct_partitions,
    )

    service = ValorantDbService(FakeDb())

    rows = await service.get_partitions(123)

    assert rows == [(8, 2)]
    assert calls[-1] == ("get_partitions", ("conn", 10, None, True))
