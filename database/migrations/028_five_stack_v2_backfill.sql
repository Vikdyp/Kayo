-- 028_five_stack_v2_backfill.sql
-- Non-destructive five-stack backfill into the v2 schema.

WITH five_stack_discord_users AS (
  SELECT leader_discord_id AS discord_id
    FROM five_stack_teams
  UNION
  SELECT member_discord_id AS discord_id
    FROM five_stack_team_members
  UNION
  SELECT discord_member_id AS discord_id
    FROM five_stack_queue
  UNION
  SELECT unnest(COALESCE(team_member_ids, '{}'::BIGINT[])) AS discord_id
    FROM five_stack_queue
  UNION
  SELECT discord_member_id AS discord_id
    FROM five_stack_match_participants
  UNION
  SELECT discord_member_id AS discord_id
    FROM five_stack_player_stats
  UNION
  SELECT reporter_id AS discord_id
    FROM five_stack_feedback
)
INSERT INTO discord_users_v2(discord_id)
SELECT DISTINCT discord_id
  FROM five_stack_discord_users
 WHERE discord_id IS NOT NULL
   AND discord_id > 0
ON CONFLICT (discord_id) DO NOTHING;

WITH five_stack_members AS (
  SELECT guild_id, leader_discord_id AS discord_id
    FROM five_stack_teams
  UNION
  SELECT guild_id, member_discord_id AS discord_id
    FROM five_stack_team_members
  UNION
  SELECT guild_id, discord_member_id AS discord_id
    FROM five_stack_queue
  UNION
  SELECT guild_id, unnest(COALESCE(team_member_ids, '{}'::BIGINT[])) AS discord_id
    FROM five_stack_queue
  UNION
  SELECT m.guild_id, p.discord_member_id AS discord_id
    FROM five_stack_match_participants p
    JOIN five_stack_matches m ON m.id = p.match_id
  UNION
  SELECT guild_id, discord_member_id AS discord_id
    FROM five_stack_player_stats
  UNION
  SELECT m.guild_id, f.reporter_id AS discord_id
    FROM five_stack_feedback f
    JOIN five_stack_matches m ON m.id = f.match_id
)
INSERT INTO guild_members_v2(guild_id, discord_user_id, legacy_user_id, is_member, left_at, updated_at)
SELECT DISTINCT fsm.guild_id, du.id, u.user_id, FALSE, now(), now()
  FROM five_stack_members fsm
  JOIN discord_users_v2 du ON du.discord_id = fsm.discord_id
  LEFT JOIN users u ON u.discord_id = fsm.discord_id
 WHERE fsm.discord_id IS NOT NULL
   AND fsm.discord_id > 0
ON CONFLICT (guild_id, discord_user_id) DO UPDATE
  SET legacy_user_id = COALESCE(guild_members_v2.legacy_user_id, EXCLUDED.legacy_user_id),
      updated_at = GREATEST(guild_members_v2.updated_at, EXCLUDED.updated_at);

INSERT INTO five_stack_teams_v2(
  guild_id,
  code,
  leader_member_id,
  visibility,
  status,
  forum_channel_id,
  thread_id,
  voice_channel_id,
  created_at,
  updated_at
)
SELECT
  fst.guild_id,
  fst.code,
  leader.id,
  CASE WHEN fst.visibility IN ('public', 'private') THEN fst.visibility ELSE 'public' END,
  CASE WHEN fst.status = 'deleted' THEN 'disbanded' ELSE 'active' END,
  fst.forum_channel_id,
  fst.thread_id,
  fst.voice_channel_id,
  fst.created_at,
  fst.updated_at
FROM five_stack_teams fst
JOIN discord_users_v2 leader_user ON leader_user.discord_id = fst.leader_discord_id
JOIN guild_members_v2 leader
  ON leader.guild_id = fst.guild_id
 AND leader.discord_user_id = leader_user.id
ON CONFLICT (guild_id, code) DO UPDATE
  SET leader_member_id = EXCLUDED.leader_member_id,
      visibility = EXCLUDED.visibility,
      status = EXCLUDED.status,
      forum_channel_id = EXCLUDED.forum_channel_id,
      thread_id = EXCLUDED.thread_id,
      voice_channel_id = EXCLUDED.voice_channel_id,
      updated_at = EXCLUDED.updated_at;

INSERT INTO five_stack_team_members_v2(team_id, member_id, joined_at)
SELECT team.id, member.id, fstm.joined_at
  FROM five_stack_team_members fstm
  JOIN five_stack_teams_v2 team
    ON team.guild_id = fstm.guild_id
   AND team.code = fstm.team_code
  JOIN discord_users_v2 member_user ON member_user.discord_id = fstm.member_discord_id
  JOIN guild_members_v2 member
    ON member.guild_id = fstm.guild_id
   AND member.discord_user_id = member_user.id
ON CONFLICT (team_id, member_id) DO UPDATE
  SET joined_at = EXCLUDED.joined_at;

INSERT INTO five_stack_queue_v2(
  id,
  guild_id,
  member_id,
  entry_type,
  team_id,
  language,
  region,
  platform,
  desired_team_size,
  mmr_extended,
  elo,
  elo_low,
  elo_high,
  queued_at
)
SELECT
  q.id::BIGINT,
  q.guild_id,
  member.id,
  CASE
    WHEN q.entry_type = 1 THEN 'solo'
    WHEN q.team_code IS NOT NULL OR q.entry_type = 5 THEN 'team'
    ELSE 'group'
  END,
  team.id,
  q.language,
  q.region,
  q.platform,
  q.desired_team_size,
  q.mmr_extended,
  q.elo,
  q.elo_low,
  q.elo_high,
  q.queued_at
FROM five_stack_queue q
JOIN discord_users_v2 member_user ON member_user.discord_id = q.discord_member_id
JOIN guild_members_v2 member
  ON member.guild_id = q.guild_id
 AND member.discord_user_id = member_user.id
LEFT JOIN five_stack_teams_v2 team
  ON team.guild_id = q.guild_id
 AND team.code = q.team_code
ON CONFLICT (id) DO UPDATE
  SET member_id = EXCLUDED.member_id,
      entry_type = EXCLUDED.entry_type,
      team_id = EXCLUDED.team_id,
      language = EXCLUDED.language,
      region = EXCLUDED.region,
      platform = EXCLUDED.platform,
      desired_team_size = EXCLUDED.desired_team_size,
      mmr_extended = EXCLUDED.mmr_extended,
      elo = EXCLUDED.elo,
      elo_low = EXCLUDED.elo_low,
      elo_high = EXCLUDED.elo_high,
      queued_at = EXCLUDED.queued_at;

INSERT INTO five_stack_queue_roles_v2(queue_id, role_key)
SELECT DISTINCT q.id, role_key.role_key
  FROM five_stack_queue q
  JOIN five_stack_queue_v2 q2 ON q2.id = q.id
 CROSS JOIN LATERAL unnest(COALESCE(q.roles, '{}'::TEXT[])) AS role_key(role_key)
 WHERE role_key.role_key IS NOT NULL
   AND length(btrim(role_key.role_key)) > 0
ON CONFLICT (queue_id, role_key) DO NOTHING;

SELECT setval(
  pg_get_serial_sequence('five_stack_queue_v2', 'id'),
  GREATEST((SELECT COALESCE(MAX(id), 1) FROM five_stack_queue_v2), 1),
  TRUE
);

INSERT INTO five_stack_matches_v2(
  id,
  guild_id,
  match_code,
  voice_channel_id,
  quality_score,
  elo_spread,
  avg_elo,
  team_size,
  language,
  region,
  platform,
  total_wait_time_seconds,
  created_at
)
SELECT
  m.id::BIGINT,
  m.guild_id,
  m.match_code,
  m.voice_channel_id,
  m.quality_score,
  m.elo_spread,
  m.avg_elo,
  m.team_size,
  m.language,
  m.region,
  m.platform,
  m.total_wait_time_seconds,
  m.created_at
FROM five_stack_matches m
ON CONFLICT (id) DO UPDATE
  SET match_code = EXCLUDED.match_code,
      voice_channel_id = EXCLUDED.voice_channel_id,
      quality_score = EXCLUDED.quality_score,
      elo_spread = EXCLUDED.elo_spread,
      avg_elo = EXCLUDED.avg_elo,
      team_size = EXCLUDED.team_size,
      language = EXCLUDED.language,
      region = EXCLUDED.region,
      platform = EXCLUDED.platform,
      total_wait_time_seconds = EXCLUDED.total_wait_time_seconds,
      created_at = EXCLUDED.created_at;

SELECT setval(
  pg_get_serial_sequence('five_stack_matches_v2', 'id'),
  GREATEST((SELECT COALESCE(MAX(id), 1) FROM five_stack_matches_v2), 1),
  TRUE
);

INSERT INTO five_stack_match_participants_v2(
  match_id,
  member_id,
  elo_at_match,
  entry_type,
  wait_time_seconds
)
SELECT
  p.match_id,
  member.id,
  p.elo_at_match,
  CASE
    WHEN p.entry_type = 1 THEN 'solo'
    WHEN p.entry_type = 5 THEN 'team'
    ELSE 'group'
  END,
  p.wait_time_seconds
FROM five_stack_match_participants p
JOIN five_stack_matches m ON m.id = p.match_id
JOIN five_stack_matches_v2 m2 ON m2.id = p.match_id
JOIN discord_users_v2 member_user ON member_user.discord_id = p.discord_member_id
JOIN guild_members_v2 member
  ON member.guild_id = m.guild_id
 AND member.discord_user_id = member_user.id
ON CONFLICT (match_id, member_id) DO UPDATE
  SET elo_at_match = EXCLUDED.elo_at_match,
      entry_type = EXCLUDED.entry_type,
      wait_time_seconds = EXCLUDED.wait_time_seconds;

INSERT INTO five_stack_match_roles_v2(match_id, member_id, role_key)
SELECT DISTINCT p.match_id, member.id, role_key.role_key
  FROM five_stack_match_participants p
  JOIN five_stack_matches m ON m.id = p.match_id
  JOIN discord_users_v2 member_user ON member_user.discord_id = p.discord_member_id
  JOIN guild_members_v2 member
    ON member.guild_id = m.guild_id
   AND member.discord_user_id = member_user.id
  JOIN five_stack_match_participants_v2 p2
    ON p2.match_id = p.match_id
   AND p2.member_id = member.id
 CROSS JOIN LATERAL unnest(COALESCE(p.roles_selected, '{}'::TEXT[])) AS role_key(role_key)
 WHERE role_key.role_key IS NOT NULL
   AND length(btrim(role_key.role_key)) > 0
ON CONFLICT (match_id, member_id, role_key) DO NOTHING;

INSERT INTO five_stack_feedback_v2(
  match_id,
  reporter_member_id,
  rating,
  feedback_type,
  issues,
  comment,
  created_at
)
SELECT
  f.match_id,
  reporter.id,
  f.rating,
  f.feedback_type,
  COALESCE(f.issues, '{}'::TEXT[]),
  f.comment,
  f.created_at
FROM five_stack_feedback f
JOIN five_stack_matches m ON m.id = f.match_id
JOIN five_stack_matches_v2 m2 ON m2.id = f.match_id
JOIN discord_users_v2 reporter_user ON reporter_user.discord_id = f.reporter_id
JOIN guild_members_v2 reporter
  ON reporter.guild_id = m.guild_id
 AND reporter.discord_user_id = reporter_user.id
ON CONFLICT (match_id, reporter_member_id) DO UPDATE
  SET rating = EXCLUDED.rating,
      feedback_type = EXCLUDED.feedback_type,
      issues = EXCLUDED.issues,
      comment = EXCLUDED.comment,
      created_at = EXCLUDED.created_at;

INSERT INTO five_stack_player_stats_v2(
  guild_id,
  member_id,
  total_matches,
  total_wait_time_seconds,
  matches_as_solo,
  matches_in_group,
  last_match_at,
  preferred_role
)
SELECT
  stats.guild_id,
  member.id,
  stats.total_matches,
  stats.total_wait_time_seconds,
  stats.matches_as_solo,
  stats.matches_in_group,
  stats.last_match_at,
  stats.preferred_role
FROM five_stack_player_stats stats
JOIN discord_users_v2 member_user ON member_user.discord_id = stats.discord_member_id
JOIN guild_members_v2 member
  ON member.guild_id = stats.guild_id
 AND member.discord_user_id = member_user.id
ON CONFLICT (guild_id, member_id) DO UPDATE
  SET total_matches = EXCLUDED.total_matches,
      total_wait_time_seconds = EXCLUDED.total_wait_time_seconds,
      matches_as_solo = EXCLUDED.matches_as_solo,
      matches_in_group = EXCLUDED.matches_in_group,
      last_match_at = EXCLUDED.last_match_at,
      preferred_role = EXCLUDED.preferred_role;
