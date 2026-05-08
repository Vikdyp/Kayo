from __future__ import annotations

import pytest

from database.schema_contract import (
    EXPECTED_INDEXES,
    EXPECTED_TABLES,
    KNOWN_EXTERNAL_MIGRATIONS,
    audit_connection,
    repo_migration_versions,
)


class FakeConnection:
    async def fetch(self, query: str):
        if "pg_catalog.pg_tables" in query:
            return [{"tablename": table} for table in EXPECTED_TABLES]
        if "information_schema.columns" in query:
            from database.schema_contract import EXPECTED_COLUMNS

            return [
                {"table_name": table, "column_name": column}
                for table, columns in EXPECTED_COLUMNS.items()
                for column in columns
            ]
        if "pg_indexes" in query:
            return [{"indexname": index} for index in EXPECTED_INDEXES]
        if "schema_migrations" in query:
            return [
                {"version": version}
                for version in sorted(repo_migration_versions() | KNOWN_EXTERNAL_MIGRATIONS)
            ]
        raise AssertionError(f"Unexpected query: {query}")

    async def fetchval(self, query: str):
        if "to_regclass" in query:
            return "schema_migrations"
        raise AssertionError(f"Unexpected query: {query}")


def test_known_external_render_migration_is_explicit() -> None:
    assert KNOWN_EXTERNAL_MIGRATIONS == frozenset({"010_refactor_valorant_ranking_tables.sql"})
    assert KNOWN_EXTERNAL_MIGRATIONS.isdisjoint(repo_migration_versions())


@pytest.mark.asyncio
async def test_schema_audit_accepts_known_render_migration() -> None:
    result = await audit_connection(FakeConnection())

    assert result.ok
    assert result.known_external_migrations == ("010_refactor_valorant_ranking_tables.sql",)
    assert result.unknown_applied_migrations == ()
