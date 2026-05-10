from __future__ import annotations

from pathlib import Path

import pytest

from database.schema_contract import (
    EXPECTED_INDEXES,
    EXPECTED_TABLES,
    KNOWN_EXTERNAL_MIGRATIONS,
    audit_connection,
    build_database_dsn_from_env,
    repo_migration_versions,
)


def _migration_text(name: str) -> str:
    return Path(f"database/migrations/{name}").read_text(encoding="utf-8").upper()


def _assert_non_destructive(migration: str) -> None:
    assert "DROP TABLE" not in migration
    assert "DELETE FROM" not in migration
    assert "TRUNCATE" not in migration


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


def test_identity_v2_migration_is_non_destructive_and_backfills() -> None:
    migration = _migration_text("022_identity_v2.sql")

    _assert_non_destructive(migration)
    assert "INSERT INTO DISCORD_USERS_V2" in migration
    assert "FROM USERS" in migration
    assert "INSERT INTO GUILD_MEMBERS_V2" in migration
    assert "FROM GUILD_MEMBERS" in migration


def test_domain_v2_schema_migration_is_schema_only() -> None:
    migration = _migration_text("023_domain_v2_schema.sql")

    _assert_non_destructive(migration)
    assert "INSERT INTO" not in migration
    assert "CREATE TABLE IF NOT EXISTS MODERATION_CASES_V2" in migration
    assert "CREATE TABLE IF NOT EXISTS VALORANT_ACCOUNTS_V2" in migration
    assert "CREATE TABLE IF NOT EXISTS FIVE_STACK_TEAMS_V2" in migration
    assert "CREATE TABLE IF NOT EXISTS TOURNAMENT_TEAM_PLAYERS_V2" in migration


def test_simple_v2_backfill_migration_is_non_destructive() -> None:
    migration = _migration_text("024_simple_v2_backfill.sql")

    _assert_non_destructive(migration)
    assert "INSERT INTO ECONOMY_PROFILES_V2" in migration
    assert "INSERT INTO REPUTATION_EVENTS_V2" in migration
    assert "INSERT INTO MESSAGE_DELETIONS_V2" in migration
    assert "INSERT INTO VALORANT_SENT_BUNDLES_V2" in migration


@pytest.mark.parametrize(
    ("name", "expected_fragments"),
    [
        (
            "025_valorant_v2_backfill.sql",
            (
                "INSERT INTO VALORANT_ACCOUNTS_V2",
                "INSERT INTO VALORANT_RANK_STATE_V2",
                "INSERT INTO VALORANT_RANK_SNAPSHOTS_V2",
            ),
        ),
        (
            "026_moderation_v2_backfill.sql",
            (
                "INSERT INTO MODERATION_CASES_V2",
                "INSERT INTO MODERATION_SANCTIONS_V2",
                "INSERT INTO MODERATION_ROLE_SNAPSHOTS_V2",
                "INSERT INTO UNBAN_REQUESTS_V2",
            ),
        ),
        (
            "027_scrims_tournaments_v2_backfill.sql",
            (
                "INSERT INTO SCRIMS_V2",
                "INSERT INTO SCRIM_PARTICIPANTS_V2",
                "INSERT INTO TOURNAMENTS_V2",
                "INSERT INTO TOURNAMENT_TEAM_PLAYERS_V2",
            ),
        ),
        (
            "028_five_stack_v2_backfill.sql",
            (
                "INSERT INTO FIVE_STACK_TEAMS_V2",
                "INSERT INTO FIVE_STACK_QUEUE_V2",
                "INSERT INTO FIVE_STACK_MATCHES_V2",
                "INSERT INTO FIVE_STACK_PLAYER_STATS_V2",
            ),
        ),
    ],
)
def test_complex_v2_backfill_migrations_are_non_destructive(name: str, expected_fragments: tuple[str, ...]) -> None:
    migration = _migration_text(name)

    _assert_non_destructive(migration)
    for fragment in expected_fragments:
        assert fragment in migration


def test_build_database_dsn_from_env_uses_test_database_when_test_mode_enabled() -> None:
    dsn = build_database_dsn_from_env(
        {
            "TEST_MODE": "true",
            "DATABASE_USER": "user@example",
            "DATABASE_PASSWORD": "p@ss:word/with%",
            "DATABASE_NAME": "prod_db",
            "DATABASE_TEST_NAME": "test/db",
            "DATABASE_HOST": "localhost",
            "DATABASE_PORT": "5433",
            "DATABASE_SSL": "true",
        }
    )

    assert dsn == "postgresql://user%40example:p%40ss%3Aword%2Fwith%25@localhost:5433/test%2Fdb?sslmode=require"


def test_build_database_dsn_from_env_reports_missing_selected_database() -> None:
    with pytest.raises(RuntimeError, match="DATABASE_TEST_NAME"):
        build_database_dsn_from_env(
            {
                "TEST_MODE": "true",
                "DATABASE_USER": "user",
                "DATABASE_PASSWORD": "password",
                "DATABASE_NAME": "prod_db",
                "DATABASE_HOST": "localhost",
            }
        )


@pytest.mark.asyncio
async def test_schema_audit_accepts_known_render_migration() -> None:
    result = await audit_connection(FakeConnection())

    assert result.ok
    assert result.known_external_migrations == ("010_refactor_valorant_ranking_tables.sql",)
    assert result.unknown_applied_migrations == ()
