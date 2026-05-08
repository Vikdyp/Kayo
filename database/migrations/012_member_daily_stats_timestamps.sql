-- 012_member_daily_stats_timestamps.sql
-- Additive repair for databases where 004 created member_daily_stats before the
-- timestamp columns reached production. Required by the repo upsert queries.

ALTER TABLE IF EXISTS member_daily_stats
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
