import pytest

from database.repos.valorant_elo_history_repo import ValorantEloHistoryRepo


class FakeConnection:
    def __init__(self):
        self.queries: list[tuple[str, tuple[object, ...]]] = []

    async def fetch(self, query: str, *args):
        self.queries.append((query, args))
        return []


@pytest.mark.asyncio
async def test_get_history_includes_unscoped_legacy_rows_for_current_puuid():
    conn = FakeConnection()

    rows = await ValorantEloHistoryRepo.get_history(conn, 10, puuid="puuid-1")

    assert rows == []
    query, args = conn.queries[0]
    assert args == (10, "puuid-1")
    assert "puuid = $2 OR (puuid IS NULL AND source = 'legacy')" in query


@pytest.mark.asyncio
async def test_get_distinct_partitions_includes_unscoped_legacy_rows_for_current_puuid():
    conn = FakeConnection()

    rows = await ValorantEloHistoryRepo.get_distinct_partitions(conn, 10, "puuid-1")

    assert rows == []
    query, args = conn.queries[0]
    assert args == (10, "puuid-1")
    assert "puuid = $2 OR (puuid IS NULL AND source = 'legacy')" in query
