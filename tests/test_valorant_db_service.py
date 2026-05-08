from __future__ import annotations

import pytest

from database.repos.valorant_info_repo import (
    ValorantInfoRepo,
    ValorantUserPresenceRow,
)
from database.services.valorant_db_service import ValorantDbService


class FakeTransaction:
    async def __aenter__(self):
        return "conn"

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeDb:
    def transaction(self):
        return FakeTransaction()


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
