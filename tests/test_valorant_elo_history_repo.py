import pytest

from database.repos.valorant_elo_history_repo import ValorantEloHistoryRepo


class FakeConnection:
    def __init__(self):
        self.queries: list[tuple[str, tuple[object, ...]]] = []

    async def fetch(self, query: str, *args):
        self.queries.append((query, args))
        return []

    async def fetchrow(self, query: str, *args):
        self.queries.append((query, args))
        return None


@pytest.mark.asyncio
async def test_get_history_filters_only_current_puuid_when_known():
    conn = FakeConnection()

    rows = await ValorantEloHistoryRepo.get_history(conn, 10, puuid="puuid-1")

    assert rows == []
    query, args = conn.queries[0]
    assert args == (10, "puuid-1")
    assert "AND puuid = $2" in query
    assert "source = 'legacy'" not in query


@pytest.mark.asyncio
async def test_get_history_can_read_only_unscoped_legacy_rows():
    conn = FakeConnection()

    rows = await ValorantEloHistoryRepo.get_history(conn, 10, legacy_only=True)

    assert rows == []
    query, args = conn.queries[0]
    assert args == (10,)
    assert "puuid IS NULL AND source = 'legacy'" in query


@pytest.mark.asyncio
async def test_get_distinct_partitions_filters_only_current_puuid_when_known():
    conn = FakeConnection()

    rows = await ValorantEloHistoryRepo.get_distinct_partitions(conn, 10, "puuid-1")

    assert rows == []
    query, args = conn.queries[0]
    assert args == (10, "puuid-1")
    assert "AND puuid = $2" in query
    assert "source = 'legacy'" not in query


@pytest.mark.asyncio
async def test_get_distinct_partitions_can_read_only_unscoped_legacy_rows():
    conn = FakeConnection()

    rows = await ValorantEloHistoryRepo.get_distinct_partitions(
        conn, 10, legacy_only=True
    )

    assert rows == []
    query, args = conn.queries[0]
    assert args == (10,)
    assert "puuid IS NULL AND source = 'legacy'" in query


@pytest.mark.asyncio
async def test_get_last_row_filters_only_current_puuid_when_known():
    conn = FakeConnection()

    row = await ValorantEloHistoryRepo.get_last_row(conn, 10, "puuid-1")

    assert row is None
    query, args = conn.queries[0]
    assert args == (10, "puuid-1")
    assert "AND puuid = $2" in query
    assert "source = 'legacy'" not in query


@pytest.mark.asyncio
async def test_get_last_row_can_read_only_unscoped_legacy_rows():
    conn = FakeConnection()

    row = await ValorantEloHistoryRepo.get_last_row(conn, 10, legacy_only=True)

    assert row is None
    query, args = conn.queries[0]
    assert args == (10,)
    assert "puuid IS NULL AND source = 'legacy'" in query
