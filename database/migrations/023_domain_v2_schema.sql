-- 023_domain_v2_schema.sql
-- Full non-destructive v2 domain schema.
--
-- This migration creates the target clean schema beside the current runtime
-- tables. Data backfills and code cutovers are intentionally split into later
-- migrations/domain changes.

-- ---------------------------------------------------------------------------
-- Core configuration
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS feature_keys_v2 (
  feature     TEXT NOT NULL,
  key         TEXT NOT NULL,
  value_type  TEXT NOT NULL CHECK (value_type IN ('channel', 'role', 'message', 'setting', 'text', 'integer', 'boolean')),
  required    BOOLEAN NOT NULL DEFAULT FALSE,
  description TEXT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (feature, key),
  CHECK (length(btrim(feature)) > 0 AND length(feature) <= 64),
  CHECK (length(btrim(key)) > 0 AND length(key) <= 100)
);

CREATE TABLE IF NOT EXISTS guild_channel_configs_v2 (
  guild_id   BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  key        TEXT NOT NULL,
  channel_id BIGINT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (guild_id, key),
  CHECK (length(btrim(key)) > 0 AND length(key) <= 100)
);

CREATE INDEX IF NOT EXISTS idx_guild_channel_configs_v2_channel_id
  ON guild_channel_configs_v2(channel_id);

CREATE TABLE IF NOT EXISTS guild_role_configs_v2 (
  guild_id   BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  key        TEXT NOT NULL,
  role_id    BIGINT NOT NULL,
  name_cache TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (guild_id, key),
  CHECK (length(btrim(key)) > 0 AND length(key) <= 100)
);

CREATE INDEX IF NOT EXISTS idx_guild_role_configs_v2_role_id
  ON guild_role_configs_v2(role_id);

CREATE TABLE IF NOT EXISTS persistent_messages_v2 (
  guild_id     BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  message_type TEXT NOT NULL,
  channel_id   BIGINT NOT NULL,
  message_id   BIGINT NOT NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (guild_id, message_type),
  CHECK (length(btrim(message_type)) > 0 AND length(message_type) <= 100)
);

CREATE INDEX IF NOT EXISTS idx_persistent_messages_v2_message_id
  ON persistent_messages_v2(message_id);

-- ---------------------------------------------------------------------------
-- Moderation and automod
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS moderation_cases_v2 (
  id                  BIGSERIAL PRIMARY KEY,
  guild_id            BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  target_member_id    BIGINT NOT NULL REFERENCES guild_members_v2(id) ON DELETE CASCADE,
  moderator_member_id BIGINT NULL REFERENCES guild_members_v2(id) ON DELETE SET NULL,
  case_type           TEXT NOT NULL CHECK (case_type IN ('ban', 'unban', 'warning', 'timeout', 'note', 'role_restore')),
  reason              TEXT NULL,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_moderation_cases_v2_target
  ON moderation_cases_v2(target_member_id);

CREATE INDEX IF NOT EXISTS idx_moderation_cases_v2_guild_created
  ON moderation_cases_v2(guild_id, created_at DESC);

CREATE TABLE IF NOT EXISTS moderation_sanctions_v2 (
  id            BIGSERIAL PRIMARY KEY,
  case_id       BIGINT NOT NULL REFERENCES moderation_cases_v2(id) ON DELETE CASCADE,
  sanction_type TEXT NOT NULL CHECK (sanction_type IN ('internal_ban', 'temporary_ban', 'permanent_ban', 'warning', 'timeout')),
  status        TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'expired', 'revoked', 'completed')),
  starts_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  ends_at       TIMESTAMPTZ NULL,
  resolved_at   TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS idx_moderation_sanctions_v2_status
  ON moderation_sanctions_v2(status, ends_at);

CREATE TABLE IF NOT EXISTS moderation_role_snapshots_v2 (
  guild_id   BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  member_id  BIGINT NOT NULL REFERENCES guild_members_v2(id) ON DELETE CASCADE,
  role_id    BIGINT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (guild_id, member_id, role_id)
);

CREATE TABLE IF NOT EXISTS unban_requests_v2 (
  id                    BIGSERIAL PRIMARY KEY,
  guild_id              BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  requester_user_id     BIGINT NOT NULL REFERENCES discord_users_v2(id) ON DELETE CASCADE,
  channel_id            BIGINT NULL,
  message_id            BIGINT NULL,
  reason                TEXT NOT NULL,
  status                TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled')),
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  resolved_at           TIMESTAMPTZ NULL,
  resolved_by_member_id BIGINT NULL REFERENCES guild_members_v2(id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_unban_requests_v2_one_pending
  ON unban_requests_v2(guild_id, requester_user_id)
  WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_unban_requests_v2_guild_status
  ON unban_requests_v2(guild_id, status);

CREATE TABLE IF NOT EXISTS automod_settings_v2 (
  guild_id                 BIGINT PRIMARY KEY REFERENCES guilds(guild_id) ON DELETE CASCADE,
  scam_detection_enabled   BOOLEAN NOT NULL DEFAULT TRUE,
  spam_detection_enabled   BOOLEAN NOT NULL DEFAULT TRUE,
  spam_channel_threshold   INTEGER NOT NULL DEFAULT 3 CHECK (spam_channel_threshold > 0),
  spam_time_window         INTEGER NOT NULL DEFAULT 10 CHECK (spam_time_window > 0),
  delete_messages_on_scam  BOOLEAN NOT NULL DEFAULT TRUE,
  delete_period_hours      INTEGER NOT NULL DEFAULT 24 CHECK (delete_period_hours > 0),
  created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS automod_allowed_roles_v2 (
  guild_id BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  role_id  BIGINT NOT NULL,
  PRIMARY KEY (guild_id, role_id)
);

CREATE INDEX IF NOT EXISTS idx_automod_allowed_roles_v2_role
  ON automod_allowed_roles_v2(role_id);

CREATE TABLE IF NOT EXISTS automod_allowed_channels_v2 (
  guild_id   BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  channel_id BIGINT NOT NULL,
  PRIMARY KEY (guild_id, channel_id)
);

CREATE INDEX IF NOT EXISTS idx_automod_allowed_channels_v2_channel
  ON automod_allowed_channels_v2(channel_id);

CREATE TABLE IF NOT EXISTS automod_scam_patterns_v2 (
  guild_id BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  pattern  TEXT NOT NULL,
  PRIMARY KEY (guild_id, pattern)
);

CREATE TABLE IF NOT EXISTS automod_scam_domains_v2 (
  guild_id BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  domain   TEXT NOT NULL,
  PRIMARY KEY (guild_id, domain)
);

-- ---------------------------------------------------------------------------
-- Valorant
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS valorant_accounts_v2 (
  id              BIGSERIAL PRIMARY KEY,
  discord_user_id BIGINT NOT NULL REFERENCES discord_users_v2(id) ON DELETE CASCADE,
  puuid           TEXT NULL UNIQUE,
  name            TEXT NOT NULL,
  tag             TEXT NOT NULL,
  region          TEXT NULL,
  platform        TEXT NULL,
  account_level   INTEGER NULL,
  card_uuid       TEXT NULL,
  title_uuid      TEXT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (discord_user_id),
  CHECK (length(btrim(name)) > 0),
  CHECK (length(btrim(tag)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_valorant_accounts_v2_user
  ON valorant_accounts_v2(discord_user_id);

CREATE INDEX IF NOT EXISTS idx_valorant_accounts_v2_puuid
  ON valorant_accounts_v2(puuid);

CREATE TABLE IF NOT EXISTS valorant_rank_state_v2 (
  account_id         BIGINT PRIMARY KEY REFERENCES valorant_accounts_v2(id) ON DELETE CASCADE,
  rank_name          TEXT NULL,
  elo                INTEGER NULL,
  season             INTEGER NULL,
  act                INTEGER NULL,
  tracking_enabled   BOOLEAN NOT NULL DEFAULT FALSE,
  is_active          BOOLEAN NOT NULL DEFAULT TRUE,
  error_count        INTEGER NOT NULL DEFAULT 0 CHECK (error_count >= 0),
  last_error_at      TIMESTAMPTZ NULL,
  last_checked_at    TIMESTAMPTZ NULL,
  last_notification  TIMESTAMPTZ NULL,
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_valorant_rank_state_v2_tracking
  ON valorant_rank_state_v2(is_active, tracking_enabled, last_checked_at);

CREATE TABLE IF NOT EXISTS valorant_rank_snapshots_v2 (
  id          BIGSERIAL PRIMARY KEY,
  account_id  BIGINT NOT NULL REFERENCES valorant_accounts_v2(id) ON DELETE CASCADE,
  season      INTEGER NOT NULL,
  act         INTEGER NOT NULL,
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  elo         INTEGER NOT NULL,
  is_win      BOOLEAN NULL,
  CHECK (season > 0),
  CHECK (act > 0)
);

CREATE INDEX IF NOT EXISTS idx_valorant_rank_snapshots_v2_account
  ON valorant_rank_snapshots_v2(account_id, season, act, recorded_at DESC);

CREATE TABLE IF NOT EXISTS valorant_sent_bundles_v2 (
  guild_id    BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  bundle_uuid TEXT NOT NULL,
  notified_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (guild_id, bundle_uuid)
);

CREATE INDEX IF NOT EXISTS idx_valorant_sent_bundles_v2_guild
  ON valorant_sent_bundles_v2(guild_id);

-- ---------------------------------------------------------------------------
-- Five-stack
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS five_stack_teams_v2 (
  id                BIGSERIAL PRIMARY KEY,
  guild_id          BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  code              TEXT NOT NULL,
  leader_member_id  BIGINT NOT NULL REFERENCES guild_members_v2(id) ON DELETE CASCADE,
  visibility        TEXT NOT NULL CHECK (visibility IN ('public', 'private')),
  status            TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disbanded', 'expired')),
  forum_channel_id  BIGINT NULL,
  thread_id         BIGINT NULL,
  voice_channel_id  BIGINT NULL,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (guild_id, code),
  UNIQUE (thread_id),
  UNIQUE (voice_channel_id)
);

CREATE INDEX IF NOT EXISTS idx_five_stack_teams_v2_guild_status
  ON five_stack_teams_v2(guild_id, status);

CREATE TABLE IF NOT EXISTS five_stack_team_members_v2 (
  team_id   BIGINT NOT NULL REFERENCES five_stack_teams_v2(id) ON DELETE CASCADE,
  member_id BIGINT NOT NULL REFERENCES guild_members_v2(id) ON DELETE CASCADE,
  joined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (team_id, member_id)
);

CREATE INDEX IF NOT EXISTS idx_five_stack_team_members_v2_member
  ON five_stack_team_members_v2(member_id);

CREATE TABLE IF NOT EXISTS five_stack_queue_v2 (
  id                 BIGSERIAL PRIMARY KEY,
  guild_id           BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  member_id          BIGINT NOT NULL REFERENCES guild_members_v2(id) ON DELETE CASCADE,
  entry_type         TEXT NOT NULL CHECK (entry_type IN ('solo', 'group', 'team')),
  team_id            BIGINT NULL REFERENCES five_stack_teams_v2(id) ON DELETE SET NULL,
  language           TEXT NULL,
  region             TEXT NULL,
  platform           TEXT NULL,
  desired_team_size  INTEGER NOT NULL DEFAULT 0 CHECK (desired_team_size IN (0, 2, 3, 5)),
  mmr_extended       BOOLEAN NULL,
  elo                INTEGER NULL,
  elo_low            INTEGER NULL,
  elo_high           INTEGER NULL,
  queued_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_five_stack_queue_v2_guild
  ON five_stack_queue_v2(guild_id, queued_at);

CREATE INDEX IF NOT EXISTS idx_five_stack_queue_v2_member
  ON five_stack_queue_v2(member_id);

CREATE TABLE IF NOT EXISTS five_stack_queue_roles_v2 (
  queue_id BIGINT NOT NULL REFERENCES five_stack_queue_v2(id) ON DELETE CASCADE,
  role_key TEXT NOT NULL,
  PRIMARY KEY (queue_id, role_key)
);

CREATE TABLE IF NOT EXISTS five_stack_matches_v2 (
  id                      BIGSERIAL PRIMARY KEY,
  guild_id                BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  match_code              TEXT NOT NULL,
  voice_channel_id        BIGINT NULL UNIQUE,
  quality_score           NUMERIC(6, 2) NULL,
  elo_spread              INTEGER NULL,
  avg_elo                 INTEGER NULL,
  team_size               INTEGER NOT NULL CHECK (team_size > 0),
  language                TEXT NULL,
  region                  TEXT NULL,
  platform                TEXT NULL,
  total_wait_time_seconds INTEGER NULL,
  created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (guild_id, match_code)
);

CREATE INDEX IF NOT EXISTS idx_five_stack_matches_v2_guild_created
  ON five_stack_matches_v2(guild_id, created_at DESC);

CREATE TABLE IF NOT EXISTS five_stack_match_participants_v2 (
  match_id          BIGINT NOT NULL REFERENCES five_stack_matches_v2(id) ON DELETE CASCADE,
  member_id         BIGINT NOT NULL REFERENCES guild_members_v2(id) ON DELETE CASCADE,
  elo_at_match      INTEGER NULL,
  entry_type        TEXT NOT NULL CHECK (entry_type IN ('solo', 'group', 'team')),
  wait_time_seconds INTEGER NULL,
  PRIMARY KEY (match_id, member_id)
);

CREATE INDEX IF NOT EXISTS idx_five_stack_participants_v2_member
  ON five_stack_match_participants_v2(member_id);

CREATE TABLE IF NOT EXISTS five_stack_match_roles_v2 (
  match_id  BIGINT NOT NULL,
  member_id BIGINT NOT NULL,
  role_key  TEXT NOT NULL,
  PRIMARY KEY (match_id, member_id, role_key),
  FOREIGN KEY (match_id, member_id)
    REFERENCES five_stack_match_participants_v2(match_id, member_id)
    ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS five_stack_feedback_v2 (
  match_id           BIGINT NOT NULL REFERENCES five_stack_matches_v2(id) ON DELETE CASCADE,
  reporter_member_id BIGINT NOT NULL REFERENCES guild_members_v2(id) ON DELETE CASCADE,
  rating             INTEGER NULL CHECK (rating BETWEEN 1 AND 5),
  feedback_type      TEXT NULL,
  issues             TEXT[] NOT NULL DEFAULT '{}',
  comment            TEXT NULL,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (match_id, reporter_member_id)
);

CREATE TABLE IF NOT EXISTS five_stack_player_stats_v2 (
  guild_id                BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  member_id               BIGINT NOT NULL REFERENCES guild_members_v2(id) ON DELETE CASCADE,
  total_matches           INTEGER NOT NULL DEFAULT 0 CHECK (total_matches >= 0),
  total_wait_time_seconds INTEGER NOT NULL DEFAULT 0 CHECK (total_wait_time_seconds >= 0),
  matches_as_solo         INTEGER NOT NULL DEFAULT 0 CHECK (matches_as_solo >= 0),
  matches_in_group        INTEGER NOT NULL DEFAULT 0 CHECK (matches_in_group >= 0),
  last_match_at           TIMESTAMPTZ NULL,
  preferred_role          TEXT NULL,
  PRIMARY KEY (guild_id, member_id)
);

CREATE INDEX IF NOT EXISTS idx_five_stack_stats_v2_matches
  ON five_stack_player_stats_v2(guild_id, total_matches DESC);

-- ---------------------------------------------------------------------------
-- Remaining domains
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS member_daily_stats_v2 (
  guild_id    BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  date        DATE NOT NULL,
  join_count  INTEGER NOT NULL DEFAULT 0 CHECK (join_count >= 0),
  leave_count INTEGER NOT NULL DEFAULT 0 CHECK (leave_count >= 0),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (guild_id, date)
);

CREATE INDEX IF NOT EXISTS idx_member_daily_stats_v2_date
  ON member_daily_stats_v2(date);

CREATE TABLE IF NOT EXISTS message_deletions_v2 (
  id                    BIGSERIAL PRIMARY KEY,
  guild_id              BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  deleted_by_member_id  BIGINT NULL REFERENCES guild_members_v2(id) ON DELETE SET NULL,
  source                TEXT NOT NULL,
  channel_id            BIGINT NULL,
  channel_name          TEXT NULL,
  deletion_type         TEXT NOT NULL,
  target_user_id        BIGINT NULL REFERENCES discord_users_v2(id) ON DELETE SET NULL,
  target_user_tag       TEXT NULL,
  message_count         INTEGER NOT NULL CHECK (message_count > 0),
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_message_deletions_v2_guild_created
  ON message_deletions_v2(guild_id, created_at DESC);

CREATE TABLE IF NOT EXISTS economy_profiles_v2 (
  guild_id         BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  member_id        BIGINT NOT NULL REFERENCES guild_members_v2(id) ON DELETE CASCADE,
  balance          INTEGER NOT NULL DEFAULT 0 CHECK (balance >= 0),
  last_daily_claim DATE NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (guild_id, member_id)
);

CREATE INDEX IF NOT EXISTS idx_economy_profiles_v2_member
  ON economy_profiles_v2(member_id);

CREATE TABLE IF NOT EXISTS economy_inventory_items_v2 (
  guild_id   BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  member_id  BIGINT NOT NULL REFERENCES guild_members_v2(id) ON DELETE CASCADE,
  item_name  TEXT NOT NULL,
  quantity   INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (guild_id, member_id, item_name),
  CHECK (length(btrim(item_name)) > 0 AND length(item_name) <= 100)
);

CREATE INDEX IF NOT EXISTS idx_economy_inventory_v2_member
  ON economy_inventory_items_v2(member_id);

CREATE TABLE IF NOT EXISTS file_counters_v2 (
  guild_id        BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  channel_id      BIGINT NOT NULL,
  message_id      BIGINT NULL,
  added_count     INTEGER NOT NULL DEFAULT 0 CHECK (added_count >= 0),
  completed_count INTEGER NOT NULL DEFAULT 0 CHECK (completed_count >= 0),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (guild_id, channel_id)
);

CREATE INDEX IF NOT EXISTS idx_file_counters_v2_message
  ON file_counters_v2(message_id);

CREATE TABLE IF NOT EXISTS reputation_events_v2 (
  id                 BIGSERIAL PRIMARY KEY,
  guild_id           BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  reporter_member_id BIGINT NOT NULL REFERENCES guild_members_v2(id) ON DELETE CASCADE,
  target_member_id   BIGINT NOT NULL REFERENCES guild_members_v2(id) ON DELETE CASCADE,
  event_type         TEXT NOT NULL CHECK (event_type IN ('report', 'recommendation')),
  event_date         DATE NOT NULL,
  count              INTEGER NOT NULL DEFAULT 1 CHECK (count > 0),
  reason             TEXT NULL,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (guild_id, reporter_member_id, target_member_id, event_type, event_date)
);

CREATE INDEX IF NOT EXISTS idx_reputation_events_v2_target
  ON reputation_events_v2(guild_id, target_member_id, event_date DESC);

CREATE INDEX IF NOT EXISTS idx_reputation_events_v2_reporter_target
  ON reputation_events_v2(guild_id, reporter_member_id, target_member_id);

CREATE TABLE IF NOT EXISTS user_profiles_v2 (
  discord_user_id   BIGINT PRIMARY KEY REFERENCES discord_users_v2(id) ON DELETE CASCADE,
  genre             TEXT NULL,
  valorant_tracker  TEXT NULL,
  lft               TEXT NULL,
  note              TEXT NULL,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_user_profiles_v2_lft
  ON user_profiles_v2(lft);

CREATE TABLE IF NOT EXISTS twitch_streamers_v2 (
  guild_id       BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  streamer_login TEXT NOT NULL,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (guild_id, streamer_login),
  CHECK (streamer_login ~ '^[a-z0-9_]{3,25}$')
);

CREATE INDEX IF NOT EXISTS idx_twitch_streamers_v2_guild
  ON twitch_streamers_v2(guild_id);

CREATE TABLE IF NOT EXISTS scrims_v2 (
  id                BIGSERIAL PRIMARY KEY,
  guild_id          BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  creator_member_id BIGINT NOT NULL REFERENCES guild_members_v2(id) ON DELETE CASCADE,
  scheduled_at      TIMESTAMPTZ NOT NULL,
  map_name          TEXT NULL,
  rank_name         TEXT NULL,
  notes             TEXT NULL,
  channel_id        BIGINT NULL,
  message_id        BIGINT NULL,
  status            TEXT NOT NULL DEFAULT 'scheduled' CHECK (status IN ('scheduled', 'completed', 'cancelled')),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  ended_at          TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS idx_scrims_v2_due
  ON scrims_v2(status, scheduled_at);

CREATE INDEX IF NOT EXISTS idx_scrims_v2_guild_status
  ON scrims_v2(guild_id, status);

CREATE INDEX IF NOT EXISTS idx_scrims_v2_message
  ON scrims_v2(message_id);

CREATE TABLE IF NOT EXISTS scrim_participants_v2 (
  scrim_id   BIGINT NOT NULL REFERENCES scrims_v2(id) ON DELETE CASCADE,
  team_index INTEGER NOT NULL CHECK (team_index IN (1, 2)),
  member_id  BIGINT NOT NULL REFERENCES guild_members_v2(id) ON DELETE CASCADE,
  PRIMARY KEY (scrim_id, member_id)
);

CREATE INDEX IF NOT EXISTS idx_scrim_participants_v2_member
  ON scrim_participants_v2(member_id);

CREATE TABLE IF NOT EXISTS tournaments_v2 (
  id                      BIGSERIAL PRIMARY KEY,
  guild_id                BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  tournament_name         TEXT NOT NULL,
  max_teams               INTEGER NOT NULL CHECK (max_teams > 0),
  registration_start      TIMESTAMPTZ NOT NULL,
  registration_end        TIMESTAMPTZ NOT NULL,
  tournament_date         TIMESTAMPTZ NOT NULL,
  status                  TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'registration', 'active', 'closed', 'cancelled')),
  registration_channel_id BIGINT NULL,
  registration_message_id BIGINT NULL,
  created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  closed_at               TIMESTAMPTZ NULL,
  CHECK (registration_start <= registration_end),
  CHECK (registration_end <= tournament_date)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_tournaments_v2_one_active
  ON tournaments_v2(guild_id)
  WHERE status IN ('registration', 'active');

CREATE INDEX IF NOT EXISTS idx_tournaments_v2_guild_status
  ON tournaments_v2(guild_id, status);

CREATE TABLE IF NOT EXISTS tournament_teams_v2 (
  id                BIGSERIAL PRIMARY KEY,
  tournament_id     BIGINT NOT NULL REFERENCES tournaments_v2(id) ON DELETE CASCADE,
  captain_member_id BIGINT NOT NULL REFERENCES guild_members_v2(id) ON DELETE CASCADE,
  team_name         TEXT NOT NULL,
  coach_member_id   BIGINT NULL REFERENCES guild_members_v2(id) ON DELETE SET NULL,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tournament_id, team_name),
  UNIQUE (tournament_id, captain_member_id)
);

CREATE INDEX IF NOT EXISTS idx_tournament_teams_v2_tournament
  ON tournament_teams_v2(tournament_id);

CREATE TABLE IF NOT EXISTS tournament_team_players_v2 (
  team_id   BIGINT NOT NULL REFERENCES tournament_teams_v2(id) ON DELETE CASCADE,
  member_id BIGINT NOT NULL REFERENCES guild_members_v2(id) ON DELETE CASCADE,
  slot_type TEXT NOT NULL CHECK (slot_type IN ('player', 'substitute')),
  PRIMARY KEY (team_id, member_id)
);

CREATE INDEX IF NOT EXISTS idx_tournament_players_v2_member
  ON tournament_team_players_v2(member_id);
