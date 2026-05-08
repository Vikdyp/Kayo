-- 010_valorant.sql
-- Valorant account linking + partitioned MMR history.
--
-- This migration is intentionally defensive because the previous Valorant table
-- may already exist from the legacy bot. Existing data is copied into a backup
-- table before any schema change, then migrated into the new users-based model
-- when the legacy user_id table is available.

DO $$
DECLARE
  has_valorant_table BOOLEAN;
  has_new_shape BOOLEAN;
BEGIN
  has_valorant_table := to_regclass('public.valorant_info') IS NOT NULL;

  IF has_valorant_table THEN
    EXECUTE 'CREATE TABLE IF NOT EXISTS valorant_info_legacy_backup AS TABLE valorant_info WITH DATA';

    SELECT EXISTS (
      SELECT 1
        FROM information_schema.columns
       WHERE table_schema = 'public'
         AND table_name = 'valorant_info'
         AND column_name = 'last_checked_at'
    ) INTO has_new_shape;

    IF NOT has_new_shape THEN
      IF to_regclass('public.valorant_info_legacy_pre_010') IS NULL THEN
        ALTER TABLE valorant_info RENAME TO valorant_info_legacy_pre_010;
      ELSE
        DROP TABLE valorant_info;
      END IF;
    END IF;
  END IF;
END $$;

-- Main table: links internal users to Valorant accounts.
CREATE TABLE IF NOT EXISTS valorant_info (
  user_id           BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
  pseudo            VARCHAR(32),
  tag               VARCHAR(16),
  puuid             VARCHAR(255),
  region            VARCHAR(10),
  platform          VARCHAR(20),
  rank              VARCHAR(50),
  elo               INTEGER,
  current_season    INTEGER,
  current_act       INTEGER,
  is_active         BOOLEAN NOT NULL DEFAULT TRUE,
  tracking_enabled  BOOLEAN NOT NULL DEFAULT FALSE,
  error_count       INTEGER NOT NULL DEFAULT 0,
  last_error_at     TIMESTAMPTZ,
  last_checked_at   TIMESTAMPTZ,
  last_notification TIMESTAMPTZ,
  deactivated_at    TIMESTAMPTZ
);

ALTER TABLE valorant_info
  ADD COLUMN IF NOT EXISTS pseudo VARCHAR(32),
  ADD COLUMN IF NOT EXISTS tag VARCHAR(16),
  ADD COLUMN IF NOT EXISTS puuid VARCHAR(255),
  ADD COLUMN IF NOT EXISTS region VARCHAR(10),
  ADD COLUMN IF NOT EXISTS platform VARCHAR(20),
  ADD COLUMN IF NOT EXISTS rank VARCHAR(50),
  ADD COLUMN IF NOT EXISTS elo INTEGER,
  ADD COLUMN IF NOT EXISTS current_season INTEGER,
  ADD COLUMN IF NOT EXISTS current_act INTEGER,
  ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS tracking_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS error_count INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS last_error_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS last_checked_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS last_notification TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS deactivated_at TIMESTAMPTZ;

-- Copy legacy Valorant rows when the old user table is still available.
DO $$
BEGIN
  IF to_regclass('public.valorant_info_legacy_pre_010') IS NOT NULL
     AND to_regclass('public.user_id') IS NOT NULL
     AND EXISTS (
       SELECT 1
         FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'user_id'
          AND column_name = 'discord_id'
     )
     AND EXISTS (
       SELECT 1
         FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'user_id'
          AND column_name = 'id'
     )
  THEN
    INSERT INTO users(user_id, discord_id)
    SELECT DISTINCT old_users.id::BIGINT, old_users.discord_id::BIGINT
      FROM user_id old_users
      JOIN valorant_info_legacy_pre_010 legacy
        ON legacy.user_id = old_users.id
     WHERE old_users.discord_id IS NOT NULL
    ON CONFLICT (discord_id) DO NOTHING;

    PERFORM setval(
      pg_get_serial_sequence('users', 'user_id'),
      GREATEST((SELECT COALESCE(MAX(user_id), 1) FROM users), 1),
      TRUE
    );

    INSERT INTO valorant_info (
      user_id,
      pseudo,
      tag,
      puuid,
      region,
      platform,
      rank,
      elo,
      is_active,
      tracking_enabled,
      last_notification,
      deactivated_at
    )
    SELECT
      new_users.user_id,
      legacy.pseudo,
      legacy.tag,
      legacy.puuid,
      legacy.region,
      NULLIF(NULLIF(lower(legacy.platforms), 'none'), ''),
      legacy.rank,
      legacy.elo,
      COALESCE(legacy.is_active, TRUE),
      COALESCE(legacy.tracking_enabled, FALSE),
      legacy.last_notification,
      legacy.deactivated_at
    FROM valorant_info_legacy_pre_010 legacy
    JOIN user_id old_users
      ON old_users.id = legacy.user_id
    JOIN users new_users
      ON new_users.discord_id = old_users.discord_id::BIGINT
    ON CONFLICT (user_id) DO UPDATE SET
      pseudo = COALESCE(EXCLUDED.pseudo, valorant_info.pseudo),
      tag = COALESCE(EXCLUDED.tag, valorant_info.tag),
      puuid = COALESCE(EXCLUDED.puuid, valorant_info.puuid),
      region = COALESCE(EXCLUDED.region, valorant_info.region),
      platform = COALESCE(EXCLUDED.platform, valorant_info.platform),
      rank = COALESCE(EXCLUDED.rank, valorant_info.rank),
      elo = COALESCE(EXCLUDED.elo, valorant_info.elo),
      is_active = EXCLUDED.is_active,
      tracking_enabled = EXCLUDED.tracking_enabled,
      last_notification = COALESCE(EXCLUDED.last_notification, valorant_info.last_notification),
      deactivated_at = EXCLUDED.deactivated_at;
  END IF;
END $$;

-- Pipeline picks oldest-checked active users with pseudo/tag.
CREATE INDEX IF NOT EXISTS idx_valorant_info_active_pipeline
  ON valorant_info (last_checked_at ASC NULLS FIRST)
  WHERE is_active = TRUE AND pseudo IS NOT NULL AND tag IS NOT NULL;

-- Fast lookup for tracked players.
CREATE INDEX IF NOT EXISTS idx_valorant_info_tracking
  ON valorant_info (user_id)
  WHERE tracking_enabled = TRUE;

-- Duplicate check by pseudo+tag.
CREATE INDEX IF NOT EXISTS idx_valorant_info_pseudo_tag
  ON valorant_info (pseudo, tag);

CREATE INDEX IF NOT EXISTS idx_valorant_info_puuid
  ON valorant_info (puuid)
  WHERE puuid IS NOT NULL;

-- Partitioned MMR history (season -> act).
CREATE TABLE IF NOT EXISTS valorant_elo_history_parent (
  season      INTEGER NOT NULL,
  act         INTEGER NOT NULL,
  user_id     BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  recorded_at TIMESTAMPTZ NOT NULL,
  elo         INTEGER NOT NULL,
  is_win      BOOLEAN NOT NULL,
  PRIMARY KEY (season, act, user_id, recorded_at)
) PARTITION BY LIST (season);
