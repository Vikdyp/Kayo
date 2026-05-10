-- 027_scrims_tournaments_v2_backfill.sql
-- Non-destructive scrims and tournaments backfill into the v2 schema.

-- Direct Discord ids stored in tournament registrations may not have legacy
-- user rows yet.
WITH tournament_discord_users AS (
  SELECT unnest(COALESCE(player_discord_ids, '{}'::BIGINT[])) AS discord_id
    FROM tournament_teams
  UNION
  SELECT unnest(COALESCE(substitute_discord_ids, '{}'::BIGINT[])) AS discord_id
    FROM tournament_teams
  UNION
  SELECT coach_discord_id AS discord_id
    FROM tournament_teams
   WHERE coach_discord_id IS NOT NULL
)
INSERT INTO discord_users_v2(discord_id)
SELECT DISTINCT discord_id
  FROM tournament_discord_users
 WHERE discord_id IS NOT NULL
   AND discord_id > 0
ON CONFLICT (discord_id) DO NOTHING;

-- Legacy user ids used by scrims and tournament captains.
INSERT INTO discord_users_v2(discord_id, legacy_user_id, created_at, last_seen_at)
SELECT u.discord_id, u.user_id, u.created_at, u.last_seen_at
  FROM users u
 WHERE u.discord_id IS NOT NULL
   AND u.user_id IN (
     SELECT creator_user_id FROM scrims WHERE creator_user_id IS NOT NULL
     UNION
     SELECT unnest(COALESCE(team1_user_ids, '{}'::BIGINT[])) FROM scrims
     UNION
     SELECT unnest(COALESCE(team2_user_ids, '{}'::BIGINT[])) FROM scrims
     UNION
     SELECT captain_user_id FROM tournament_teams
   )
ON CONFLICT (discord_id) DO UPDATE
  SET legacy_user_id = COALESCE(discord_users_v2.legacy_user_id, EXCLUDED.legacy_user_id),
      last_seen_at = CASE
        WHEN discord_users_v2.last_seen_at IS NULL THEN EXCLUDED.last_seen_at
        WHEN EXCLUDED.last_seen_at IS NULL THEN discord_users_v2.last_seen_at
        ELSE GREATEST(discord_users_v2.last_seen_at, EXCLUDED.last_seen_at)
      END;

WITH legacy_members AS (
  SELECT guild_id, creator_user_id AS user_id
    FROM scrims
   WHERE creator_user_id IS NOT NULL
  UNION
  SELECT guild_id, unnest(COALESCE(team1_user_ids, '{}'::BIGINT[])) AS user_id
    FROM scrims
  UNION
  SELECT guild_id, unnest(COALESCE(team2_user_ids, '{}'::BIGINT[])) AS user_id
    FROM scrims
  UNION
  SELECT guild_id, captain_user_id AS user_id
    FROM tournament_teams
)
INSERT INTO guild_members_v2(guild_id, discord_user_id, legacy_user_id, is_member, left_at, updated_at)
SELECT DISTINCT lm.guild_id, du.id, lm.user_id, FALSE, now(), now()
  FROM legacy_members lm
  JOIN users u ON u.user_id = lm.user_id
  JOIN discord_users_v2 du ON du.discord_id = u.discord_id
ON CONFLICT (guild_id, discord_user_id) DO UPDATE
  SET legacy_user_id = COALESCE(guild_members_v2.legacy_user_id, EXCLUDED.legacy_user_id),
      updated_at = GREATEST(guild_members_v2.updated_at, EXCLUDED.updated_at);

WITH tournament_discord_members AS (
  SELECT guild_id, unnest(COALESCE(player_discord_ids, '{}'::BIGINT[])) AS discord_id
    FROM tournament_teams
  UNION
  SELECT guild_id, unnest(COALESCE(substitute_discord_ids, '{}'::BIGINT[])) AS discord_id
    FROM tournament_teams
  UNION
  SELECT guild_id, coach_discord_id AS discord_id
    FROM tournament_teams
   WHERE coach_discord_id IS NOT NULL
)
INSERT INTO guild_members_v2(guild_id, discord_user_id, legacy_user_id, is_member, left_at, updated_at)
SELECT DISTINCT tdm.guild_id, du.id, u.user_id, FALSE, now(), now()
  FROM tournament_discord_members tdm
  JOIN discord_users_v2 du ON du.discord_id = tdm.discord_id
  LEFT JOIN users u ON u.discord_id = tdm.discord_id
 WHERE tdm.discord_id IS NOT NULL
   AND tdm.discord_id > 0
ON CONFLICT (guild_id, discord_user_id) DO UPDATE
  SET legacy_user_id = COALESCE(guild_members_v2.legacy_user_id, EXCLUDED.legacy_user_id),
      updated_at = GREATEST(guild_members_v2.updated_at, EXCLUDED.updated_at);

WITH scrim_sources AS (
  SELECT
    s.*,
    COALESCE(s.creator_user_id, s.team1_user_ids[1], s.team2_user_ids[1]) AS resolved_creator_user_id
  FROM scrims s
)
INSERT INTO scrims_v2(
  id,
  guild_id,
  creator_member_id,
  scheduled_at,
  map_name,
  rank_name,
  notes,
  channel_id,
  message_id,
  status,
  created_at,
  updated_at,
  ended_at
)
SELECT
  ss.id::BIGINT,
  ss.guild_id,
  creator.id,
  ss.scheduled_at,
  ss.map_name,
  ss.rank_name,
  ss.notes,
  ss.channel_id,
  ss.message_id,
  CASE WHEN ss.status = 'active' THEN 'scheduled' ELSE ss.status END,
  ss.created_at,
  ss.updated_at,
  ss.ended_at
FROM scrim_sources ss
JOIN guild_members_v2 creator
  ON creator.guild_id = ss.guild_id
 AND creator.legacy_user_id = ss.resolved_creator_user_id
WHERE ss.resolved_creator_user_id IS NOT NULL
  AND ss.status IN ('active', 'completed', 'cancelled')
ON CONFLICT (id) DO UPDATE
  SET creator_member_id = EXCLUDED.creator_member_id,
      scheduled_at = EXCLUDED.scheduled_at,
      map_name = EXCLUDED.map_name,
      rank_name = EXCLUDED.rank_name,
      notes = EXCLUDED.notes,
      channel_id = EXCLUDED.channel_id,
      message_id = EXCLUDED.message_id,
      status = EXCLUDED.status,
      updated_at = EXCLUDED.updated_at,
      ended_at = EXCLUDED.ended_at;

WITH scrim_participants AS (
  SELECT id AS scrim_id, guild_id, 1 AS team_index, unnest(COALESCE(team1_user_ids, '{}'::BIGINT[])) AS user_id
    FROM scrims
  UNION
  SELECT id AS scrim_id, guild_id, 2 AS team_index, unnest(COALESCE(team2_user_ids, '{}'::BIGINT[])) AS user_id
    FROM scrims
)
INSERT INTO scrim_participants_v2(scrim_id, team_index, member_id)
SELECT sp.scrim_id, sp.team_index, gm2.id
  FROM scrim_participants sp
  JOIN scrims_v2 s2 ON s2.id = sp.scrim_id
  JOIN guild_members_v2 gm2
    ON gm2.guild_id = sp.guild_id
   AND gm2.legacy_user_id = sp.user_id
ON CONFLICT (scrim_id, member_id) DO UPDATE
  SET team_index = EXCLUDED.team_index;

SELECT setval(
  pg_get_serial_sequence('scrims_v2', 'id'),
  GREATEST((SELECT COALESCE(MAX(id), 1) FROM scrims_v2), 1),
  TRUE
);

INSERT INTO tournaments_v2(
  id,
  guild_id,
  tournament_name,
  max_teams,
  registration_start,
  registration_end,
  tournament_date,
  status,
  registration_channel_id,
  registration_message_id,
  created_at,
  updated_at,
  closed_at
)
SELECT
  t.id::BIGINT,
  t.guild_id,
  t.tournament_name,
  t.max_teams,
  t.registration_start,
  t.registration_end,
  GREATEST(t.tournament_date, t.registration_end),
  CASE WHEN t.status = 'active' THEN 'registration' ELSE 'closed' END,
  t.registration_channel_id,
  t.registration_message_id,
  t.created_at,
  t.updated_at,
  t.closed_at
FROM tournaments t
WHERE t.status IN ('active', 'closed')
ON CONFLICT (id) DO UPDATE
  SET tournament_name = EXCLUDED.tournament_name,
      max_teams = EXCLUDED.max_teams,
      registration_start = EXCLUDED.registration_start,
      registration_end = EXCLUDED.registration_end,
      tournament_date = EXCLUDED.tournament_date,
      status = EXCLUDED.status,
      registration_channel_id = EXCLUDED.registration_channel_id,
      registration_message_id = EXCLUDED.registration_message_id,
      updated_at = EXCLUDED.updated_at,
      closed_at = EXCLUDED.closed_at;

SELECT setval(
  pg_get_serial_sequence('tournaments_v2', 'id'),
  GREATEST((SELECT COALESCE(MAX(id), 1) FROM tournaments_v2), 1),
  TRUE
);

INSERT INTO tournament_teams_v2(
  id,
  tournament_id,
  captain_member_id,
  team_name,
  coach_member_id,
  created_at,
  updated_at
)
SELECT
  tt.id::BIGINT,
  tt.tournament_id,
  captain.id,
  tt.team_name,
  coach.id,
  tt.created_at,
  tt.updated_at
FROM tournament_teams tt
JOIN tournaments_v2 t2 ON t2.id = tt.tournament_id
JOIN guild_members_v2 captain
  ON captain.guild_id = tt.guild_id
 AND captain.legacy_user_id = tt.captain_user_id
LEFT JOIN discord_users_v2 coach_user ON coach_user.discord_id = tt.coach_discord_id
LEFT JOIN guild_members_v2 coach
  ON coach.guild_id = tt.guild_id
 AND coach.discord_user_id = coach_user.id
ON CONFLICT (id) DO UPDATE
  SET captain_member_id = EXCLUDED.captain_member_id,
      team_name = EXCLUDED.team_name,
      coach_member_id = EXCLUDED.coach_member_id,
      updated_at = EXCLUDED.updated_at;

SELECT setval(
  pg_get_serial_sequence('tournament_teams_v2', 'id'),
  GREATEST((SELECT COALESCE(MAX(id), 1) FROM tournament_teams_v2), 1),
  TRUE
);

WITH raw_players AS (
  SELECT tt.id AS legacy_team_id, tt.guild_id, unnest(COALESCE(tt.player_discord_ids, '{}'::BIGINT[])) AS discord_id, 'player' AS slot_type, 1 AS slot_rank
    FROM tournament_teams tt
  UNION ALL
  SELECT tt.id AS legacy_team_id, tt.guild_id, unnest(COALESCE(tt.substitute_discord_ids, '{}'::BIGINT[])) AS discord_id, 'substitute' AS slot_type, 2 AS slot_rank
    FROM tournament_teams tt
),
deduped_players AS (
  SELECT legacy_team_id, guild_id, discord_id, slot_type
    FROM (
      SELECT
        raw_players.*,
        row_number() OVER (PARTITION BY legacy_team_id, discord_id ORDER BY slot_rank) AS rn
      FROM raw_players
      WHERE discord_id IS NOT NULL
        AND discord_id > 0
    ) ranked
   WHERE rn = 1
)
INSERT INTO tournament_team_players_v2(team_id, member_id, slot_type)
SELECT team.id, gm2.id, dp.slot_type
  FROM deduped_players dp
  JOIN tournament_teams_v2 team ON team.id = dp.legacy_team_id
  JOIN discord_users_v2 du ON du.discord_id = dp.discord_id
  JOIN guild_members_v2 gm2
    ON gm2.guild_id = dp.guild_id
   AND gm2.discord_user_id = du.id
ON CONFLICT (team_id, member_id) DO UPDATE
  SET slot_type = EXCLUDED.slot_type;
