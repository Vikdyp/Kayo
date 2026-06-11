-- 029_mmr_history_metadata.sql
-- Add account-scoped MMR history metadata without removing legacy data.

ALTER TABLE IF EXISTS valorant_elo_history_parent
  ADD COLUMN IF NOT EXISTS puuid VARCHAR(255),
  ADD COLUMN IF NOT EXISTS rr_delta INTEGER,
  ADD COLUMN IF NOT EXISTS match_id VARCHAR(128),
  ADD COLUMN IF NOT EXISTS source VARCHAR(32) NOT NULL DEFAULT 'legacy';

ALTER TABLE IF EXISTS valorant_info
  ADD COLUMN IF NOT EXISTS mmr_history_backfilled_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS mmr_history_backfill_attempted_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS mmr_history_backfill_error TEXT;

-- Legacy history rows stay unscoped when their PUUID was not known at write time.
-- Stamping all old rows with the currently linked PUUID would permanently attach
-- previous-account history to the current account for users who changed accounts.

WITH history_diffs AS (
  SELECT
    season,
    act,
    user_id,
    recorded_at,
    elo - LAG(elo) OVER (
      PARTITION BY user_id
      ORDER BY recorded_at, season, act
    ) AS computed_rr_delta
  FROM valorant_elo_history_parent
)
UPDATE valorant_elo_history_parent h
   SET rr_delta = d.computed_rr_delta
  FROM history_diffs d
 WHERE h.season = d.season
   AND h.act = d.act
   AND h.user_id = d.user_id
   AND h.recorded_at = d.recorded_at
   AND h.rr_delta IS NULL
   AND d.computed_rr_delta IS NOT NULL;

UPDATE valorant_elo_history_parent
   SET source = 'legacy'
 WHERE source IS NULL;

CREATE INDEX IF NOT EXISTS idx_valorant_elo_history_user_puuid_recorded_at
  ON valorant_elo_history_parent (user_id, puuid, recorded_at DESC);
