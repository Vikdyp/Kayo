-- 004_member_daily_stats.sql
-- Stats quotidiennes join/leave par guild (date en UTC)

DO $$
BEGIN
  IF to_regclass('public.member_daily_stats') IS NOT NULL
     AND NOT EXISTS (
       SELECT 1
         FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'member_daily_stats'
          AND column_name = 'guild_id'
     )
  THEN
    EXECUTE 'CREATE TABLE IF NOT EXISTS member_daily_stats_legacy_backup AS TABLE member_daily_stats WITH DATA';
    IF to_regclass('public.member_daily_stats_legacy_pre_004') IS NULL THEN
      ALTER TABLE member_daily_stats RENAME TO member_daily_stats_legacy_pre_004;
    ELSE
      DROP TABLE member_daily_stats;
    END IF;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS member_daily_stats (
    guild_id    BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
    date        DATE NOT NULL,
    join_count  INTEGER NOT NULL DEFAULT 0 CHECK (join_count >= 0),
    leave_count INTEGER NOT NULL DEFAULT 0 CHECK (leave_count >= 0),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, date)
);

CREATE INDEX IF NOT EXISTS idx_member_daily_stats_date
    ON member_daily_stats(guild_id, date DESC);
