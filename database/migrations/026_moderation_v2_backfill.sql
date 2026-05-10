-- 026_moderation_v2_backfill.sql
-- Non-destructive moderation and unban-request backfill into the v2 schema.

-- Refresh identities for moderation users.
INSERT INTO discord_users_v2(discord_id, legacy_user_id, created_at, last_seen_at)
SELECT u.discord_id, u.user_id, u.created_at, u.last_seen_at
  FROM users u
 WHERE u.discord_id IS NOT NULL
   AND u.user_id IN (
     SELECT user_id FROM moderation_bans
     UNION
     SELECT banned_by_user_id FROM moderation_bans
     UNION
     SELECT user_id FROM moderation_warnings
     UNION
     SELECT warned_by_user_id FROM moderation_warnings
     UNION
     SELECT user_id FROM moderation_role_backups
     UNION
     SELECT requester_user_id FROM unban_requests
     UNION
     SELECT resolved_by_user_id FROM unban_requests WHERE resolved_by_user_id IS NOT NULL
   )
ON CONFLICT (discord_id) DO UPDATE
  SET legacy_user_id = COALESCE(discord_users_v2.legacy_user_id, EXCLUDED.legacy_user_id),
      last_seen_at = CASE
        WHEN discord_users_v2.last_seen_at IS NULL THEN EXCLUDED.last_seen_at
        WHEN EXCLUDED.last_seen_at IS NULL THEN discord_users_v2.last_seen_at
        ELSE GREATEST(discord_users_v2.last_seen_at, EXCLUDED.last_seen_at)
      END;

WITH moderation_members AS (
  SELECT guild_id, user_id FROM moderation_bans
  UNION
  SELECT guild_id, banned_by_user_id AS user_id FROM moderation_bans
  UNION
  SELECT guild_id, user_id FROM moderation_warnings
  UNION
  SELECT guild_id, warned_by_user_id AS user_id FROM moderation_warnings
  UNION
  SELECT guild_id, user_id FROM moderation_role_backups
  UNION
  SELECT guild_id, requester_user_id AS user_id FROM unban_requests
  UNION
  SELECT guild_id, resolved_by_user_id AS user_id
    FROM unban_requests
   WHERE resolved_by_user_id IS NOT NULL
)
INSERT INTO guild_members_v2(guild_id, discord_user_id, legacy_user_id, is_member, left_at, updated_at)
SELECT DISTINCT mm.guild_id, du.id, mm.user_id, FALSE, now(), now()
  FROM moderation_members mm
  JOIN users u ON u.user_id = mm.user_id
  JOIN discord_users_v2 du ON du.discord_id = u.discord_id
ON CONFLICT (guild_id, discord_user_id) DO UPDATE
  SET legacy_user_id = COALESCE(guild_members_v2.legacy_user_id, EXCLUDED.legacy_user_id),
      updated_at = GREATEST(guild_members_v2.updated_at, EXCLUDED.updated_at);

WITH inserted_ban_cases AS (
  INSERT INTO moderation_cases_v2(
    guild_id,
    target_member_id,
    moderator_member_id,
    case_type,
    reason,
    created_at
  )
  SELECT
    mb.guild_id,
    target.id,
    moderator.id,
    'ban',
    mb.reason,
    mb.banned_at
  FROM moderation_bans mb
  JOIN guild_members_v2 target
    ON target.guild_id = mb.guild_id
   AND target.legacy_user_id = mb.user_id
  LEFT JOIN guild_members_v2 moderator
    ON moderator.guild_id = mb.guild_id
   AND moderator.legacy_user_id = mb.banned_by_user_id
  WHERE NOT EXISTS (
    SELECT 1
      FROM moderation_cases_v2 existing
     WHERE existing.guild_id = mb.guild_id
       AND existing.target_member_id = target.id
       AND existing.case_type = 'ban'
       AND existing.created_at = mb.banned_at
  )
  RETURNING id, guild_id, target_member_id, created_at
)
INSERT INTO moderation_sanctions_v2(
  case_id,
  sanction_type,
  status,
  starts_at,
  ends_at,
  resolved_at
)
SELECT
  inserted.id,
  CASE
    WHEN mb.ban_type = 'temp' THEN 'temporary_ban'
    WHEN mb.ban_type = 'soft' THEN 'internal_ban'
    ELSE 'permanent_ban'
  END,
  CASE
    WHEN mb.ban_end IS NOT NULL AND mb.ban_end <= now() THEN 'expired'
    ELSE 'active'
  END,
  mb.banned_at,
  mb.ban_end,
  CASE WHEN mb.ban_end IS NOT NULL AND mb.ban_end <= now() THEN mb.ban_end ELSE NULL END
FROM inserted_ban_cases inserted
JOIN guild_members_v2 target ON target.id = inserted.target_member_id
JOIN moderation_bans mb
  ON mb.guild_id = inserted.guild_id
 AND mb.user_id = target.legacy_user_id
 AND mb.banned_at = inserted.created_at;

WITH inserted_warning_cases AS (
  INSERT INTO moderation_cases_v2(
    guild_id,
    target_member_id,
    moderator_member_id,
    case_type,
    reason,
    created_at
  )
  SELECT
    mw.guild_id,
    target.id,
    moderator.id,
    'warning',
    mw.reason,
    mw.created_at
  FROM moderation_warnings mw
  JOIN guild_members_v2 target
    ON target.guild_id = mw.guild_id
   AND target.legacy_user_id = mw.user_id
  LEFT JOIN guild_members_v2 moderator
    ON moderator.guild_id = mw.guild_id
   AND moderator.legacy_user_id = mw.warned_by_user_id
  WHERE NOT EXISTS (
    SELECT 1
      FROM moderation_cases_v2 existing
     WHERE existing.guild_id = mw.guild_id
       AND existing.target_member_id = target.id
       AND existing.case_type = 'warning'
       AND existing.created_at = mw.created_at
  )
  RETURNING id, guild_id, target_member_id, created_at
)
INSERT INTO moderation_sanctions_v2(case_id, sanction_type, status, starts_at)
SELECT inserted.id, 'warning', 'active', inserted.created_at
  FROM inserted_warning_cases inserted;

INSERT INTO moderation_role_snapshots_v2(guild_id, member_id, role_id, created_at)
SELECT rb.guild_id, gm2.id, role_id.role_id, rb.created_at
  FROM moderation_role_backups rb
  JOIN guild_members_v2 gm2
    ON gm2.guild_id = rb.guild_id
   AND gm2.legacy_user_id = rb.user_id
 CROSS JOIN LATERAL unnest(rb.roles) AS role_id(role_id)
 WHERE role_id.role_id IS NOT NULL
ON CONFLICT (guild_id, member_id, role_id) DO UPDATE
  SET created_at = EXCLUDED.created_at;

INSERT INTO unban_requests_v2(
  id,
  guild_id,
  requester_user_id,
  channel_id,
  message_id,
  reason,
  status,
  created_at,
  resolved_at,
  resolved_by_member_id
)
SELECT
  ur.id::BIGINT,
  ur.guild_id,
  requester.id,
  ur.channel_id,
  ur.message_id,
  COALESCE(ur.reason, ''),
  CASE
    WHEN ur.status = 'accepted' THEN 'approved'
    WHEN ur.status = 'rejected' THEN 'rejected'
    ELSE 'pending'
  END,
  ur.created_at,
  ur.resolved_at,
  resolver.id
FROM unban_requests ur
JOIN users requester_user ON requester_user.user_id = ur.requester_user_id
JOIN discord_users_v2 requester ON requester.discord_id = requester_user.discord_id
LEFT JOIN guild_members_v2 resolver
  ON resolver.guild_id = ur.guild_id
 AND resolver.legacy_user_id = ur.resolved_by_user_id
ON CONFLICT (id) DO UPDATE
  SET requester_user_id = EXCLUDED.requester_user_id,
      channel_id = EXCLUDED.channel_id,
      message_id = EXCLUDED.message_id,
      reason = EXCLUDED.reason,
      status = EXCLUDED.status,
      created_at = EXCLUDED.created_at,
      resolved_at = EXCLUDED.resolved_at,
      resolved_by_member_id = EXCLUDED.resolved_by_member_id;

SELECT setval(
  pg_get_serial_sequence('unban_requests_v2', 'id'),
  GREATEST((SELECT COALESCE(MAX(id), 1) FROM unban_requests_v2), 1),
  TRUE
);
