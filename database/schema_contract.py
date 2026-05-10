from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import asyncpg
from dotenv import load_dotenv

from database.dsn import build_database_dsn_from_env
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
        "discord_users_v2",
        "economy_inventory_items",
        "economy_profiles",
        "file_counters",
        "five_stack_feedback",
        "five_stack_match_participants",
        "five_stack_matches",
        "five_stack_player_stats",
        "five_stack_queue",
        "five_stack_team_members",
        "five_stack_teams",
        "guild_channels",
        "guild_members",
        "guild_members_v2",
        "guild_roles",
        "guilds",
        "member_daily_stats",
        "message_deletions",
        "moderation_bans",
        "moderation_role_backups",
        "moderation_warnings",
        "persistent_messages",
        "reputation_events",
        "role_combinations",
        "schema_migrations",
        "scrims",
        "tournament_teams",
        "tournaments",
        "twitch_streamers",
        "unban_requests",
        "users",
        "user_profiles",
        "valorant_elo_history_parent",
        "valorant_info",
        "valorant_sent_bundles",
    }
)

EXPECTED_DOMAIN_V2_TABLES = frozenset(
    {
        "automod_allowed_channels_v2",
        "automod_allowed_roles_v2",
        "automod_scam_domains_v2",
        "automod_scam_patterns_v2",
        "automod_settings_v2",
        "economy_inventory_items_v2",
        "economy_profiles_v2",
        "feature_keys_v2",
        "file_counters_v2",
        "five_stack_feedback_v2",
        "five_stack_match_participants_v2",
        "five_stack_match_roles_v2",
        "five_stack_matches_v2",
        "five_stack_player_stats_v2",
        "five_stack_queue_roles_v2",
        "five_stack_queue_v2",
        "five_stack_team_members_v2",
        "five_stack_teams_v2",
        "guild_channel_configs_v2",
        "guild_role_configs_v2",
        "member_daily_stats_v2",
        "message_deletions_v2",
        "moderation_cases_v2",
        "moderation_role_snapshots_v2",
        "moderation_sanctions_v2",
        "persistent_messages_v2",
        "reputation_events_v2",
        "scrim_participants_v2",
        "scrims_v2",
        "tournament_team_players_v2",
        "tournament_teams_v2",
        "tournaments_v2",
        "twitch_streamers_v2",
        "unban_requests_v2",
        "user_profiles_v2",
        "valorant_accounts_v2",
        "valorant_rank_snapshots_v2",
        "valorant_rank_state_v2",
        "valorant_sent_bundles_v2",
    }
)

EXPECTED_TABLES = EXPECTED_TABLES | EXPECTED_DOMAIN_V2_TABLES


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
    "discord_users_v2": frozenset({"id", "discord_id", "legacy_user_id", "created_at", "last_seen_at"}),
    "guild_members_v2": frozenset(
        {
            "id",
            "guild_id",
            "discord_user_id",
            "legacy_user_id",
            "is_member",
            "joined_at",
            "left_at",
            "accepted_rules",
            "accepted_rules_at",
            "updated_at",
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
    "economy_profiles": frozenset(
        {
            "guild_id",
            "user_id",
            "balance",
            "last_daily_claim",
            "created_at",
            "updated_at",
        }
    ),
    "economy_inventory_items": frozenset(
        {
            "guild_id",
            "user_id",
            "item_name",
            "quantity",
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
    "five_stack_teams": frozenset(
        {
            "code",
            "guild_id",
            "leader_discord_id",
            "visibility",
            "forum_channel_id",
            "thread_id",
            "voice_channel_id",
            "status",
            "created_at",
            "updated_at",
        }
    ),
    "five_stack_team_members": frozenset({"guild_id", "team_code", "member_discord_id", "joined_at"}),
    "five_stack_queue": frozenset(
        {
            "id",
            "guild_id",
            "discord_member_id",
            "entry_type",
            "team_code",
            "team_member_ids",
            "language",
            "region",
            "platform",
            "desired_team_size",
            "mmr_extended",
            "elo",
            "elo_high",
            "elo_low",
            "roles",
            "queued_at",
        }
    ),
    "five_stack_matches": frozenset(
        {
            "id",
            "guild_id",
            "match_code",
            "voice_channel_id",
            "quality_score",
            "elo_spread",
            "avg_elo",
            "role_diversity_score",
            "total_wait_time_seconds",
            "team_size",
            "language",
            "region",
            "platform",
            "created_at",
        }
    ),
    "five_stack_match_participants": frozenset(
        {
            "match_id",
            "discord_member_id",
            "elo_at_match",
            "roles_selected",
            "entry_type",
            "wait_time_seconds",
        }
    ),
    "five_stack_player_stats": frozenset(
        {
            "guild_id",
            "discord_member_id",
            "total_matches",
            "total_wait_time_seconds",
            "matches_as_solo",
            "matches_in_group",
            "last_match_at",
            "preferred_role",
        }
    ),
    "five_stack_feedback": frozenset(
        {
            "match_id",
            "reporter_id",
            "rating",
            "feedback_type",
            "issues",
            "comment",
            "created_at",
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
    "role_combinations": frozenset(
        {
            "id",
            "guild_id",
            "primary_role_id",
            "secondary_role_id",
            "combined_role_id",
            "created_at",
            "updated_at",
        }
    ),
    "scrims": frozenset(
        {
            "id",
            "guild_id",
            "creator_user_id",
            "scheduled_at",
            "map_name",
            "rank_name",
            "notes",
            "team1_user_ids",
            "team2_user_ids",
            "channel_id",
            "message_id",
            "status",
            "created_at",
            "updated_at",
            "ended_at",
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
    "twitch_streamers": frozenset(
        {
            "guild_id",
            "streamer_login",
            "created_at",
            "updated_at",
        }
    ),
    "tournaments": frozenset(
        {
            "id",
            "guild_id",
            "tournament_name",
            "max_teams",
            "registration_start",
            "registration_end",
            "tournament_date",
            "status",
            "registration_channel_id",
            "registration_message_id",
            "created_at",
            "updated_at",
            "closed_at",
        }
    ),
    "tournament_teams": frozenset(
        {
            "id",
            "tournament_id",
            "guild_id",
            "captain_user_id",
            "team_name",
            "player_discord_ids",
            "substitute_discord_ids",
            "coach_discord_id",
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
    "valorant_sent_bundles": frozenset({"guild_id", "bundle_uuid", "notified_at"}),
}

EXPECTED_DOMAIN_V2_COLUMNS: Mapping[str, frozenset[str]] = {
    "feature_keys_v2": frozenset({"feature", "key", "value_type", "required", "description", "created_at"}),
    "guild_channel_configs_v2": frozenset({"guild_id", "key", "channel_id", "created_at", "updated_at"}),
    "guild_role_configs_v2": frozenset({"guild_id", "key", "role_id", "name_cache", "created_at", "updated_at"}),
    "persistent_messages_v2": frozenset(
        {"guild_id", "message_type", "channel_id", "message_id", "created_at", "updated_at"}
    ),
    "moderation_cases_v2": frozenset(
        {"id", "guild_id", "target_member_id", "moderator_member_id", "case_type", "reason", "created_at"}
    ),
    "moderation_sanctions_v2": frozenset(
        {"id", "case_id", "sanction_type", "status", "starts_at", "ends_at", "resolved_at"}
    ),
    "moderation_role_snapshots_v2": frozenset({"guild_id", "member_id", "role_id", "created_at"}),
    "unban_requests_v2": frozenset(
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
            "resolved_by_member_id",
        }
    ),
    "automod_settings_v2": frozenset(
        {
            "guild_id",
            "scam_detection_enabled",
            "spam_detection_enabled",
            "spam_channel_threshold",
            "spam_time_window",
            "delete_messages_on_scam",
            "delete_period_hours",
            "created_at",
            "updated_at",
        }
    ),
    "automod_allowed_roles_v2": frozenset({"guild_id", "role_id"}),
    "automod_allowed_channels_v2": frozenset({"guild_id", "channel_id"}),
    "automod_scam_patterns_v2": frozenset({"guild_id", "pattern"}),
    "automod_scam_domains_v2": frozenset({"guild_id", "domain"}),
    "valorant_accounts_v2": frozenset(
        {
            "id",
            "discord_user_id",
            "puuid",
            "name",
            "tag",
            "region",
            "platform",
            "account_level",
            "card_uuid",
            "title_uuid",
            "created_at",
            "updated_at",
        }
    ),
    "valorant_rank_state_v2": frozenset(
        {
            "account_id",
            "rank_name",
            "elo",
            "season",
            "act",
            "tracking_enabled",
            "is_active",
            "error_count",
            "last_error_at",
            "last_checked_at",
            "last_notification",
            "updated_at",
        }
    ),
    "valorant_rank_snapshots_v2": frozenset(
        {"id", "account_id", "season", "act", "recorded_at", "elo", "is_win"}
    ),
    "valorant_sent_bundles_v2": frozenset({"guild_id", "bundle_uuid", "notified_at"}),
    "five_stack_teams_v2": frozenset(
        {
            "id",
            "guild_id",
            "code",
            "leader_member_id",
            "visibility",
            "status",
            "forum_channel_id",
            "thread_id",
            "voice_channel_id",
            "created_at",
            "updated_at",
        }
    ),
    "five_stack_team_members_v2": frozenset({"team_id", "member_id", "joined_at"}),
    "five_stack_queue_v2": frozenset(
        {
            "id",
            "guild_id",
            "member_id",
            "entry_type",
            "team_id",
            "language",
            "region",
            "platform",
            "desired_team_size",
            "mmr_extended",
            "elo",
            "elo_low",
            "elo_high",
            "queued_at",
        }
    ),
    "five_stack_queue_roles_v2": frozenset({"queue_id", "role_key"}),
    "five_stack_matches_v2": frozenset(
        {
            "id",
            "guild_id",
            "match_code",
            "voice_channel_id",
            "quality_score",
            "elo_spread",
            "avg_elo",
            "team_size",
            "language",
            "region",
            "platform",
            "total_wait_time_seconds",
            "created_at",
        }
    ),
    "five_stack_match_participants_v2": frozenset(
        {"match_id", "member_id", "elo_at_match", "entry_type", "wait_time_seconds"}
    ),
    "five_stack_match_roles_v2": frozenset({"match_id", "member_id", "role_key"}),
    "five_stack_feedback_v2": frozenset(
        {"match_id", "reporter_member_id", "rating", "feedback_type", "issues", "comment", "created_at"}
    ),
    "five_stack_player_stats_v2": frozenset(
        {
            "guild_id",
            "member_id",
            "total_matches",
            "total_wait_time_seconds",
            "matches_as_solo",
            "matches_in_group",
            "last_match_at",
            "preferred_role",
        }
    ),
    "member_daily_stats_v2": frozenset({"guild_id", "date", "join_count", "leave_count", "created_at", "updated_at"}),
    "message_deletions_v2": frozenset(
        {
            "id",
            "guild_id",
            "deleted_by_member_id",
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
    "economy_profiles_v2": frozenset(
        {"guild_id", "member_id", "balance", "last_daily_claim", "created_at", "updated_at"}
    ),
    "economy_inventory_items_v2": frozenset(
        {"guild_id", "member_id", "item_name", "quantity", "created_at", "updated_at"}
    ),
    "file_counters_v2": frozenset(
        {"guild_id", "channel_id", "message_id", "added_count", "completed_count", "created_at", "updated_at"}
    ),
    "reputation_events_v2": frozenset(
        {
            "id",
            "guild_id",
            "reporter_member_id",
            "target_member_id",
            "event_type",
            "event_date",
            "count",
            "reason",
            "created_at",
            "updated_at",
        }
    ),
    "user_profiles_v2": frozenset(
        {"discord_user_id", "genre", "valorant_tracker", "lft", "note", "created_at", "updated_at"}
    ),
    "twitch_streamers_v2": frozenset({"guild_id", "streamer_login", "created_at", "updated_at"}),
    "scrims_v2": frozenset(
        {
            "id",
            "guild_id",
            "creator_member_id",
            "scheduled_at",
            "map_name",
            "rank_name",
            "notes",
            "channel_id",
            "message_id",
            "status",
            "created_at",
            "updated_at",
            "ended_at",
        }
    ),
    "scrim_participants_v2": frozenset({"scrim_id", "team_index", "member_id"}),
    "tournaments_v2": frozenset(
        {
            "id",
            "guild_id",
            "tournament_name",
            "max_teams",
            "registration_start",
            "registration_end",
            "tournament_date",
            "status",
            "registration_channel_id",
            "registration_message_id",
            "created_at",
            "updated_at",
            "closed_at",
        }
    ),
    "tournament_teams_v2": frozenset(
        {"id", "tournament_id", "captain_member_id", "team_name", "coach_member_id", "created_at", "updated_at"}
    ),
    "tournament_team_players_v2": frozenset({"team_id", "member_id", "slot_type"}),
}

EXPECTED_COLUMNS = {**EXPECTED_COLUMNS, **EXPECTED_DOMAIN_V2_COLUMNS}


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
        "idx_discord_users_v2_discord_id",
        "idx_discord_users_v2_legacy_user_id",
        "idx_guild_members_v2_discord_user_id",
        "idx_guild_members_v2_guild_active",
        "idx_guild_members_v2_legacy_user_id",
        "idx_guild_members_v2_rules_acceptance",
        "idx_member_daily_stats_date",
        "idx_persistent_messages_message_id",
        "idx_message_deletions_guild_id",
        "idx_message_deletions_created_at",
        "idx_economy_profiles_user_id",
        "idx_economy_inventory_user_id",
        "idx_file_counters_message_id",
        "idx_five_stack_match_participants_member",
        "idx_five_stack_matches_guild_created",
        "idx_five_stack_player_stats_matches",
        "idx_five_stack_queue_guild",
        "idx_five_stack_team_members_member",
        "idx_five_stack_teams_guild_status",
        "idx_moderation_bans_ban_end",
        "idx_moderation_bans_guild_id",
        "idx_moderation_warnings_guild_user",
        "idx_unban_requests_one_pending_per_user",
        "idx_unban_requests_guild_status",
        "idx_unban_requests_message_id",
        "idx_reputation_events_reporter_target",
        "idx_reputation_events_target",
        "idx_role_combinations_guild_id",
        "idx_scrims_due",
        "idx_scrims_guild_status",
        "idx_scrims_message_id",
        "idx_tournaments_one_active_per_guild",
        "idx_tournaments_guild_status",
        "idx_tournament_teams_tournament_id",
        "idx_tournament_teams_guild_id",
        "idx_twitch_streamers_guild_id",
        "idx_valorant_info_active_pipeline",
        "idx_valorant_info_tracking",
        "idx_valorant_info_pseudo_tag",
        "idx_valorant_info_puuid",
        "idx_valorant_sent_bundles_guild_id",
    }
)

EXPECTED_DOMAIN_V2_INDEXES = frozenset(
    {
        "idx_automod_allowed_channels_v2_channel",
        "idx_automod_allowed_roles_v2_role",
        "idx_economy_inventory_v2_member",
        "idx_economy_profiles_v2_member",
        "idx_file_counters_v2_message",
        "idx_five_stack_matches_v2_guild_created",
        "idx_five_stack_participants_v2_member",
        "idx_five_stack_queue_v2_guild",
        "idx_five_stack_queue_v2_member",
        "idx_five_stack_stats_v2_matches",
        "idx_five_stack_team_members_v2_member",
        "idx_five_stack_teams_v2_guild_status",
        "idx_guild_channel_configs_v2_channel_id",
        "idx_guild_role_configs_v2_role_id",
        "idx_member_daily_stats_v2_date",
        "idx_message_deletions_v2_guild_created",
        "idx_moderation_cases_v2_guild_created",
        "idx_moderation_cases_v2_target",
        "idx_moderation_sanctions_v2_status",
        "idx_persistent_messages_v2_message_id",
        "idx_reputation_events_v2_reporter_target",
        "idx_reputation_events_v2_target",
        "idx_scrim_participants_v2_member",
        "idx_scrims_v2_due",
        "idx_scrims_v2_guild_status",
        "idx_scrims_v2_message",
        "idx_tournament_players_v2_member",
        "idx_tournament_teams_v2_tournament",
        "idx_tournaments_v2_guild_status",
        "idx_tournaments_v2_one_active",
        "idx_twitch_streamers_v2_guild",
        "idx_unban_requests_v2_guild_status",
        "idx_unban_requests_v2_one_pending",
        "idx_user_profiles_v2_lft",
        "idx_valorant_accounts_v2_puuid",
        "idx_valorant_accounts_v2_user",
        "idx_valorant_rank_snapshots_v2_account",
        "idx_valorant_rank_state_v2_tracking",
        "idx_valorant_sent_bundles_v2_guild",
    }
)

EXPECTED_INDEXES = EXPECTED_INDEXES | EXPECTED_DOMAIN_V2_INDEXES


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
