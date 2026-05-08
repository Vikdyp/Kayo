-- 011_valorant_forward_compat.sql
-- Forward-only safety net for environments where an earlier 010 was already
-- marked applied. It avoids destructive changes and only fills missing columns,
-- backups, and indexes.

DO $$
DECLARE
  has_legacy_columns BOOLEAN;
BEGIN
  IF to_regclass('public.valorant_info') IS NULL THEN
    RETURN;
  END IF;

  SELECT EXISTS (
    SELECT 1
      FROM information_schema.columns
     WHERE table_schema = 'public'
       AND table_name = 'valorant_info'
       AND column_name IN ('needs_update', 'platforms')
  ) INTO has_legacy_columns;

  IF has_legacy_columns THEN
    EXECUTE 'CREATE TABLE IF NOT EXISTS valorant_info_legacy_backup_011 AS TABLE valorant_info WITH DATA';
  END IF;
END $$;

ALTER TABLE IF EXISTS valorant_info
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

DO $$
BEGIN
  IF to_regclass('public.valorant_info') IS NOT NULL
     AND EXISTS (
       SELECT 1
         FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'valorant_info'
          AND column_name = 'platforms'
     )
  THEN
    UPDATE valorant_info
       SET platform = NULLIF(NULLIF(lower(platforms), 'none'), '')
     WHERE platform IS NULL;
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_valorant_info_active_pipeline
  ON valorant_info (last_checked_at ASC NULLS FIRST)
  WHERE is_active = TRUE AND pseudo IS NOT NULL AND tag IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_valorant_info_tracking
  ON valorant_info (user_id)
  WHERE tracking_enabled = TRUE;

CREATE INDEX IF NOT EXISTS idx_valorant_info_pseudo_tag
  ON valorant_info (pseudo, tag);

CREATE INDEX IF NOT EXISTS idx_valorant_info_puuid
  ON valorant_info (puuid)
  WHERE puuid IS NOT NULL;

CREATE TABLE IF NOT EXISTS valorant_elo_history_parent (
  season      INTEGER NOT NULL,
  act         INTEGER NOT NULL,
  user_id     BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  recorded_at TIMESTAMPTZ NOT NULL,
  elo         INTEGER NOT NULL,
  is_win      BOOLEAN NOT NULL,
  PRIMARY KEY (season, act, user_id, recorded_at)
) PARTITION BY LIST (season);
