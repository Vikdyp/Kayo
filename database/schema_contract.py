from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import quote

import asyncpg
from dotenv import load_dotenv

from database.migrate import MIGRATIONS_DIR

load_dotenv()


KNOWN_EXTERNAL_MIGRATIONS = frozenset(
    {
        # Applied on Render before the current forward-only 010/011 Valorant
        # migrations were committed. Keep it accepted for live audits, but do
        # not recreate it or edit schema_migrations.
        "010_refactor_valorant_ranking_tables.sql",
    }
)


EXPECTED_TABLES = frozenset(
    {
        "automod_config",
        "file_counters",
        "guild_channels",
        "guild_members",
        "guild_roles",
        "guilds",
        "member_daily_stats",
        "message_deletions",
        "moderation_bans",
        "moderation_role_backups",
        "moderation_warnings",
        "persistent_messages",
        "reputation_events",
        "schema_migrations",
        "unban_requests",
        "users",
        "user_profiles",
        "valorant_elo_history_parent",
        "valorant_info",
    }
)


EXPECTED_COLUMNS: Mapping[str, frozenset[str]] = {
    "schema_migrations": frozenset({"version", "applied_at"}),
    "guilds": frozenset({"guild_id", "name_cache", "created_at", "updated_at"}),
    "guild_channels": frozenset({"guild_id", "key", "channel_id", "created_at", "updated_at"}),
    "guild_roles": frozenset({"guild_id", "key", "role_id", "name_cache", "created_at", "updated_at"}),
    "users": frozenset({"user_id", "discord_id", "created_at", "last_seen_at"}),
    "guild_members": frozenset(
        {
            "guild_id",
            "user_id",
            "is_member",
            "joined_at",
            "left_at",
            "updated_at",
            "accepted_rules",
            "accepted_rules_at",
        }
    ),
    "member_daily_stats": frozenset({"guild_id", "date", "join_count", "leave_count", "created_at", "updated_at"}),
    "persistent_messages": frozenset({"guild_id", "message_type", "channel_id", "message_id", "created_at", "updated_at"}),
    "message_deletions": frozenset(
        {
            "id",
            "guild_id",
            "deleted_by_user_id",
            "source",
            "channel_id",
            "channel_name",
            "deletion_type",
            "target_user_id",
            "target_user_tag",
            "message_count",
            "created_at",
        }
    ),
    "automod_config": frozenset(
        {
            "guild_id",
            "scam_detection_enabled",
            "spam_detection_enabled",
            "spam_channel_threshold",
            "spam_time_window",
            "delete_messages_on_scam",
            "delete_period_hours",
            "whitelisted_roles",
            "whitelisted_channels",
            "custom_scam_patterns",
            "custom_scam_domains",
            "created_at",
            "updated_at",
        }
    ),
    "file_counters": frozenset(
        {
            "guild_id",
            "channel_id",
            "message_id",
            "added_count",
            "completed_count",
            "created_at",
            "updated_at",
        }
    ),
    "reputation_events": frozenset(
        {
            "id",
            "guild_id",
            "reporter_user_id",
            "target_user_id",
            "event_type",
            "event_date",
            "count",
            "reason",
            "created_at",
            "updated_at",
        }
    ),
    "moderation_bans": frozenset(
        {
            "id",
            "guild_id",
            "user_id",
            "ban_type",
            "reason",
            "banned_by_user_id",
            "banned_at",
            "ban_end",
        }
    ),
    "moderation_warnings": frozenset({"id", "guild_id", "user_id", "warned_by_user_id", "reason", "created_at"}),
    "moderation_role_backups": frozenset({"guild_id", "user_id", "roles", "created_at"}),
    "unban_requests": frozenset(
        {
            "id",
            "guild_id",
            "requester_user_id",
            "channel_id",
            "message_id",
            "reason",
            "status",
            "created_at",
            "resolved_at",
            "resolved_by_user_id",
        }
    ),
    "user_profiles": frozenset(
        {
            "user_id",
            "genre",
            "valorant_tracker",
            "lft",
            "note",
            "created_at",
            "updated_at",
        }
    ),
    "valorant_info": frozenset(
        {
            "user_id",
            "pseudo",
            "tag",
            "puuid",
            "region",
            "platform",
            "rank",
            "elo",
            "current_season",
            "current_act",
            "is_active",
            "tracking_enabled",
            "error_count",
            "last_error_at",
            "last_checked_at",
            "last_notification",
            "deactivated_at",
        }
    ),
    "valorant_elo_history_parent": frozenset({"season", "act", "user_id", "recorded_at", "elo", "is_win"}),
}


EXPECTED_INDEXES = frozenset(
    {
        "idx_guild_channels_channel_id",
        "idx_guild_channels_guild_id",
        "idx_guild_roles_guild_id",
        "idx_guild_roles_role_id",
        "idx_users_discord_id",
        "idx_guild_members_user_id",
        "idx_guild_members_guild_active",
        "idx_guild_members_rules_acceptance",
        "idx_member_daily_stats_date",
        "idx_persistent_messages_message_id",
        "idx_message_deletions_guild_id",
        "idx_message_deletions_created_at",
        "idx_file_counters_message_id",
        "idx_moderation_bans_ban_end",
        "idx_moderation_bans_guild_id",
        "idx_moderation_warnings_guild_user",
        "idx_unban_requests_one_pending_per_user",
        "idx_unban_requests_guild_status",
        "idx_unban_requests_message_id",
        "idx_reputation_events_reporter_target",
        "idx_reputation_events_target",
        "idx_valorant_info_active_pipeline",
        "idx_valorant_info_tracking",
        "idx_valorant_info_pseudo_tag",
        "idx_valorant_info_puuid",
    }
)


@dataclass(frozen=True, slots=True)
class SchemaAuditResult:
    missing_tables: tuple[str, ...]
    missing_columns: Mapping[str, tuple[str, ...]]
    missing_indexes: tuple[str, ...]
    missing_repo_migrations: tuple[str, ...]
    unknown_applied_migrations: tuple[str, ...]
    known_external_migrations: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not (
            self.missing_tables
            or self.missing_columns
            or self.missing_indexes
            or self.missing_repo_migrations
            or self.unknown_applied_migrations
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "missing_tables": list(self.missing_tables),
            "missing_columns": {table: list(columns) for table, columns in self.missing_columns.items()},
            "missing_indexes": list(self.missing_indexes),
            "missing_repo_migrations": list(self.missing_repo_migrations),
            "unknown_applied_migrations": list(self.unknown_applied_migrations),
            "known_external_migrations": list(self.known_external_migrations),
        }


def repo_migration_versions(migrations_dir: Path = MIGRATIONS_DIR) -> frozenset[str]:
    return frozenset(path.name for path in migrations_dir.glob("*.sql") if path.is_file())


def build_database_dsn_from_env(env: Mapping[str, str] | None = None) -> str:
    values = env or os.environ
    direct_dsn = values.get("DATABASE_URL") or values.get("POSTGRES_DSN")
    if direct_dsn:
        return direct_dsn

    user = values.get("DATABASE_USER")
    password = values.get("DATABASE_PASSWORD")
    host = values.get("DATABASE_HOST")
    name = values.get("DATABASE_NAME")
    port = values.get("DATABASE_PORT", "5432")
    ssl_enabled = values.get("DATABASE_SSL", "false").strip().lower() in {"true", "1", "t", "yes", "y", "on"}

    missing = [
        key
        for key, value in {
            "DATABASE_USER": user,
            "DATABASE_PASSWORD": password,
            "DATABASE_HOST": host,
            "DATABASE_NAME": name,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing database config env vars: {', '.join(missing)}")

    dsn = f"postgresql://{quote(user)}:{quote(password)}@{host}:{port}/{name}"
    if ssl_enabled:
        dsn += "?sslmode=require"
    return dsn


async def audit_connection(
    conn: asyncpg.Connection,
    *,
    repo_migrations: Sequence[str] | None = None,
    known_external_migrations: frozenset[str] = KNOWN_EXTERNAL_MIGRATIONS,
) -> SchemaAuditResult:
    tables = {
        row["tablename"]
        for row in await conn.fetch(
            """
            SELECT tablename
              FROM pg_catalog.pg_tables
             WHERE schemaname = 'public';
            """
        )
    }
    columns = await _fetch_columns(conn)
    indexes = {
        row["indexname"]
        for row in await conn.fetch(
            """
            SELECT indexname
              FROM pg_indexes
             WHERE schemaname = 'public';
            """
        )
    }
    applied_migrations = await _fetch_applied_migrations(conn)
    repo_versions = frozenset(repo_migrations) if repo_migrations is not None else repo_migration_versions()

    missing_columns = {
        table: tuple(sorted(expected - columns.get(table, frozenset())))
        for table, expected in EXPECTED_COLUMNS.items()
        if expected - columns.get(table, frozenset())
    }
    known_present = applied_migrations & known_external_migrations

    return SchemaAuditResult(
        missing_tables=tuple(sorted(EXPECTED_TABLES - tables)),
        missing_columns=missing_columns,
        missing_indexes=tuple(sorted(EXPECTED_INDEXES - indexes)),
        missing_repo_migrations=tuple(sorted(repo_versions - applied_migrations)),
        unknown_applied_migrations=tuple(sorted(applied_migrations - repo_versions - known_external_migrations)),
        known_external_migrations=tuple(sorted(known_present)),
    )


async def audit_dsn(dsn: str) -> SchemaAuditResult:
    conn = await asyncpg.connect(dsn)
    try:
        return await audit_connection(conn)
    finally:
        await conn.close()


async def _fetch_columns(conn: asyncpg.Connection) -> dict[str, frozenset[str]]:
    rows = await conn.fetch(
        """
        SELECT table_name, column_name
          FROM information_schema.columns
         WHERE table_schema = 'public';
        """
    )
    columns: dict[str, set[str]] = {}
    for row in rows:
        columns.setdefault(row["table_name"], set()).add(row["column_name"])
    return {table: frozenset(table_columns) for table, table_columns in columns.items()}


async def _fetch_applied_migrations(conn: asyncpg.Connection) -> frozenset[str]:
    migrations_table = await conn.fetchval("SELECT to_regclass('public.schema_migrations');")
    if migrations_table is None:
        return frozenset()

    rows = await conn.fetch("SELECT version FROM schema_migrations;")
    return frozenset(row["version"] for row in rows)


async def _amain() -> int:
    parser = argparse.ArgumentParser(description="Audit the expected Kayo database schema without writing to it.")
    parser.add_argument("--json", action="store_true", help="Print the audit result as JSON.")
    args = parser.parse_args()

    result = await audit_dsn(build_database_dsn_from_env())
    payload = result.to_dict()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("OK" if result.ok else "DRIFT")
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_amain()))
