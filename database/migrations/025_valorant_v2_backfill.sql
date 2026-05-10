-- 025_valorant_v2_backfill.sql
-- Non-destructive Valorant backfill into the v2 schema.

-- Refresh identities in case the old runtime wrote new Valorant rows after 024.
INSERT INTO discord_users_v2(discord_id, legacy_user_id, created_at, last_seen_at)
SELECT u.discord_id, u.user_id, u.created_at, u.last_seen_at
  FROM users u
  JOIN valorant_info vi ON vi.user_id = u.user_id
 WHERE u.discord_id IS NOT NULL
ON CONFLICT (discord_id) DO UPDATE
  SET legacy_user_id = COALESCE(discord_users_v2.legacy_user_id, EXCLUDED.legacy_user_id),
      last_seen_at = CASE
        WHEN discord_users_v2.last_seen_at IS NULL THEN EXCLUDED.last_seen_at
        WHEN EXCLUDED.last_seen_at IS NULL THEN discord_users_v2.last_seen_at
        ELSE GREATEST(discord_users_v2.last_seen_at, EXCLUDED.last_seen_at)
      END;

WITH normalized_accounts AS (
  SELECT
    du.id AS discord_user_id,
    NULLIF(btrim(vi.puuid), '') AS puuid,
    btrim(vi.pseudo) AS name,
    btrim(vi.tag) AS tag,
    NULLIF(btrim(vi.region), '') AS region,
    NULLIF(btrim(vi.platform), '') AS platform,
    COALESCE(u.created_at, now()) AS created_at,
    COALESCE(vi.last_checked_at, vi.last_notification, u.last_seen_at, now()) AS updated_at
  FROM valorant_info vi
  JOIN users u ON u.user_id = vi.user_id
  JOIN discord_users_v2 du ON du.discord_id = u.discord_id
  WHERE NULLIF(btrim(vi.pseudo), '') IS NOT NULL
    AND NULLIF(btrim(vi.tag), '') IS NOT NULL
),
deduped_accounts AS (
  SELECT
    discord_user_id,
    CASE
      WHEN puuid IS NOT NULL AND count(*) OVER (PARTITION BY lower(puuid)) = 1 THEN puuid
      ELSE NULL
    END AS safe_puuid,
    name,
    tag,
    region,
    platform,
    created_at,
    updated_at
  FROM normalized_accounts
)
INSERT INTO valorant_accounts_v2(
  discord_user_id,
  puuid,
  name,
  tag,
  region,
  platform,
  created_at,
  updated_at
)
SELECT
  discord_user_id,
  safe_puuid,
  name,
  tag,
  region,
  platform,
  created_at,
  updated_at
FROM deduped_accounts
ON CONFLICT (discord_user_id) DO UPDATE
  SET puuid = COALESCE(EXCLUDED.puuid, valorant_accounts_v2.puuid),
      name = EXCLUDED.name,
      tag = EXCLUDED.tag,
      region = EXCLUDED.region,
      platform = EXCLUDED.platform,
      updated_at = EXCLUDED.updated_at;

INSERT INTO valorant_rank_state_v2(
  account_id,
  rank_name,
  elo,
  season,
  act,
  tracking_enabled,
  is_active,
  error_count,
  last_error_at,
  last_checked_at,
  last_notification,
  updated_at
)
SELECT
  va.id,
  vi.rank,
  vi.elo,
  vi.current_season,
  vi.current_act,
  COALESCE(vi.tracking_enabled, FALSE),
  COALESCE(vi.is_active, TRUE),
  COALESCE(vi.error_count, 0),
  vi.last_error_at,
  vi.last_checked_at,
  vi.last_notification,
  COALESCE(vi.last_checked_at, vi.last_notification, now())
FROM valorant_info vi
JOIN users u ON u.user_id = vi.user_id
JOIN discord_users_v2 du ON du.discord_id = u.discord_id
JOIN valorant_accounts_v2 va ON va.discord_user_id = du.id
ON CONFLICT (account_id) DO UPDATE
  SET rank_name = EXCLUDED.rank_name,
      elo = EXCLUDED.elo,
      season = EXCLUDED.season,
      act = EXCLUDED.act,
      tracking_enabled = EXCLUDED.tracking_enabled,
      is_active = EXCLUDED.is_active,
      error_count = EXCLUDED.error_count,
      last_error_at = EXCLUDED.last_error_at,
      last_checked_at = EXCLUDED.last_checked_at,
      last_notification = EXCLUDED.last_notification,
      updated_at = EXCLUDED.updated_at;

INSERT INTO valorant_rank_snapshots_v2(account_id, season, act, recorded_at, elo, is_win)
SELECT
  va.id,
  h.season,
  h.act,
  h.recorded_at,
  h.elo,
  h.is_win
FROM valorant_elo_history_parent h
JOIN users u ON u.user_id = h.user_id
JOIN discord_users_v2 du ON du.discord_id = u.discord_id
JOIN valorant_accounts_v2 va ON va.discord_user_id = du.id
WHERE h.season > 0
  AND h.act > 0
  AND NOT EXISTS (
    SELECT 1
      FROM valorant_rank_snapshots_v2 existing
     WHERE existing.account_id = va.id
       AND existing.season = h.season
       AND existing.act = h.act
       AND existing.recorded_at = h.recorded_at
  );
