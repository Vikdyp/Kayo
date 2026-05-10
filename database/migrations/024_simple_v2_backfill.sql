-- 024_simple_v2_backfill.sql
-- Non-destructive backfill for low-risk v2 tables.
--
-- Complex domains (moderation cases, Valorant rank history, scrims,
-- tournaments, five-stack) are intentionally left for dedicated migrations.

-- Refresh identity v2 in case the old runtime wrote new rows after 022.
INSERT INTO guilds(guild_id)
SELECT guild_id FROM guild_members
UNION
SELECT guild_id FROM guild_channels
UNION
SELECT guild_id FROM guild_roles
UNION
SELECT guild_id FROM persistent_messages
UNION
SELECT guild_id FROM automod_config
UNION
SELECT guild_id FROM member_daily_stats
UNION
SELECT guild_id FROM file_counters
UNION
SELECT guild_id FROM twitch_streamers
UNION
SELECT guild_id FROM valorant_sent_bundles
UNION
SELECT guild_id FROM economy_profiles
UNION
SELECT guild_id FROM reputation_events
UNION
SELECT guild_id FROM message_deletions
UNION
SELECT guild_id FROM moderation_bans
UNION
SELECT guild_id FROM moderation_warnings
UNION
SELECT guild_id FROM moderation_role_backups
UNION
SELECT guild_id FROM unban_requests
UNION
SELECT guild_id FROM scrims
UNION
SELECT guild_id FROM tournaments
UNION
SELECT guild_id FROM tournament_teams
UNION
SELECT guild_id FROM five_stack_teams
UNION
SELECT guild_id FROM five_stack_team_members
UNION
SELECT guild_id FROM five_stack_queue
UNION
SELECT guild_id FROM five_stack_matches
UNION
SELECT guild_id FROM five_stack_player_stats
WHERE guild_id IS NOT NULL
ON CONFLICT (guild_id) DO NOTHING;

INSERT INTO discord_users_v2(discord_id, legacy_user_id, created_at, last_seen_at)
SELECT u.discord_id, u.user_id, u.created_at, u.last_seen_at
  FROM users u
 WHERE u.discord_id IS NOT NULL
ON CONFLICT (discord_id) DO UPDATE
  SET legacy_user_id = COALESCE(discord_users_v2.legacy_user_id, EXCLUDED.legacy_user_id),
      last_seen_at = CASE
        WHEN discord_users_v2.last_seen_at IS NULL THEN EXCLUDED.last_seen_at
        WHEN EXCLUDED.last_seen_at IS NULL THEN discord_users_v2.last_seen_at
        ELSE GREATEST(discord_users_v2.last_seen_at, EXCLUDED.last_seen_at)
      END;

INSERT INTO guild_members_v2(
  guild_id,
  discord_user_id,
  legacy_user_id,
  is_member,
  joined_at,
  left_at,
  accepted_rules,
  accepted_rules_at,
  updated_at
)
SELECT
  gm.guild_id,
  du.id,
  gm.user_id,
  gm.is_member,
  gm.joined_at,
  gm.left_at,
  gm.accepted_rules,
  gm.accepted_rules_at,
  gm.updated_at
FROM guild_members gm
JOIN users u ON u.user_id = gm.user_id
JOIN discord_users_v2 du ON du.discord_id = u.discord_id
ON CONFLICT (guild_id, discord_user_id) DO UPDATE
  SET legacy_user_id = EXCLUDED.legacy_user_id,
      is_member = EXCLUDED.is_member,
      joined_at = EXCLUDED.joined_at,
      left_at = EXCLUDED.left_at,
      accepted_rules = EXCLUDED.accepted_rules,
      accepted_rules_at = EXCLUDED.accepted_rules_at,
      updated_at = EXCLUDED.updated_at;

-- Some old domain tables have users without a guild_members row. Create
-- inactive placeholders so v2 foreign keys can preserve those rows.
WITH domain_members AS (
  SELECT guild_id, user_id FROM economy_profiles
  UNION
  SELECT guild_id, reporter_user_id AS user_id FROM reputation_events
  UNION
  SELECT guild_id, target_user_id AS user_id FROM reputation_events
  UNION
  SELECT guild_id, deleted_by_user_id AS user_id
    FROM message_deletions
   WHERE deleted_by_user_id IS NOT NULL
)
INSERT INTO guild_members_v2(guild_id, discord_user_id, legacy_user_id, is_member, left_at, updated_at)
SELECT DISTINCT dm.guild_id, du.id, dm.user_id, FALSE, now(), now()
  FROM domain_members dm
  JOIN users u ON u.user_id = dm.user_id
  JOIN discord_users_v2 du ON du.discord_id = u.discord_id
ON CONFLICT (guild_id, discord_user_id) DO NOTHING;

-- Core configuration.
INSERT INTO guild_channel_configs_v2(guild_id, key, channel_id, created_at, updated_at)
SELECT guild_id, key, channel_id, created_at, updated_at
  FROM guild_channels
ON CONFLICT (guild_id, key) DO UPDATE
  SET channel_id = EXCLUDED.channel_id,
      updated_at = EXCLUDED.updated_at;

INSERT INTO guild_role_configs_v2(guild_id, key, role_id, name_cache, created_at, updated_at)
SELECT guild_id, key, role_id, name_cache, created_at, updated_at
  FROM guild_roles
ON CONFLICT (guild_id, key) DO UPDATE
  SET role_id = EXCLUDED.role_id,
      name_cache = EXCLUDED.name_cache,
      updated_at = EXCLUDED.updated_at;

INSERT INTO persistent_messages_v2(guild_id, message_type, channel_id, message_id, created_at, updated_at)
SELECT guild_id, message_type, channel_id, message_id, created_at, updated_at
  FROM persistent_messages
ON CONFLICT (guild_id, message_type) DO UPDATE
  SET channel_id = EXCLUDED.channel_id,
      message_id = EXCLUDED.message_id,
      updated_at = EXCLUDED.updated_at;

-- Automod.
INSERT INTO automod_settings_v2(
  guild_id,
  scam_detection_enabled,
  spam_detection_enabled,
  spam_channel_threshold,
  spam_time_window,
  delete_messages_on_scam,
  delete_period_hours,
  created_at,
  updated_at
)
SELECT
  guild_id,
  scam_detection_enabled,
  spam_detection_enabled,
  spam_channel_threshold,
  spam_time_window,
  delete_messages_on_scam,
  delete_period_hours,
  created_at,
  updated_at
FROM automod_config
ON CONFLICT (guild_id) DO UPDATE
  SET scam_detection_enabled = EXCLUDED.scam_detection_enabled,
      spam_detection_enabled = EXCLUDED.spam_detection_enabled,
      spam_channel_threshold = EXCLUDED.spam_channel_threshold,
      spam_time_window = EXCLUDED.spam_time_window,
      delete_messages_on_scam = EXCLUDED.delete_messages_on_scam,
      delete_period_hours = EXCLUDED.delete_period_hours,
      updated_at = EXCLUDED.updated_at;

INSERT INTO automod_allowed_roles_v2(guild_id, role_id)
SELECT a.guild_id, role_id.role_id
  FROM automod_config a
 CROSS JOIN LATERAL unnest(a.whitelisted_roles) AS role_id(role_id)
 WHERE role_id.role_id IS NOT NULL
ON CONFLICT (guild_id, role_id) DO NOTHING;

INSERT INTO automod_allowed_channels_v2(guild_id, channel_id)
SELECT a.guild_id, channel_id.channel_id
  FROM automod_config a
 CROSS JOIN LATERAL unnest(a.whitelisted_channels) AS channel_id(channel_id)
 WHERE channel_id.channel_id IS NOT NULL
ON CONFLICT (guild_id, channel_id) DO NOTHING;

INSERT INTO automod_scam_patterns_v2(guild_id, pattern)
SELECT a.guild_id, pattern.pattern
  FROM automod_config a
 CROSS JOIN LATERAL unnest(a.custom_scam_patterns) AS pattern(pattern)
 WHERE pattern.pattern IS NOT NULL
   AND length(btrim(pattern.pattern)) > 0
ON CONFLICT (guild_id, pattern) DO NOTHING;

INSERT INTO automod_scam_domains_v2(guild_id, domain)
SELECT a.guild_id, domain.domain
  FROM automod_config a
 CROSS JOIN LATERAL unnest(a.custom_scam_domains) AS domain(domain)
 WHERE domain.domain IS NOT NULL
   AND length(btrim(domain.domain)) > 0
ON CONFLICT (guild_id, domain) DO NOTHING;

-- Low-risk operational tables.
INSERT INTO member_daily_stats_v2(guild_id, date, join_count, leave_count, created_at, updated_at)
SELECT guild_id, date, join_count, leave_count, created_at, updated_at
  FROM member_daily_stats
ON CONFLICT (guild_id, date) DO UPDATE
  SET join_count = EXCLUDED.join_count,
      leave_count = EXCLUDED.leave_count,
      updated_at = EXCLUDED.updated_at;

INSERT INTO file_counters_v2(guild_id, channel_id, message_id, added_count, completed_count, created_at, updated_at)
SELECT guild_id, channel_id, message_id, added_count, completed_count, created_at, updated_at
  FROM file_counters
ON CONFLICT (guild_id, channel_id) DO UPDATE
  SET message_id = EXCLUDED.message_id,
      added_count = EXCLUDED.added_count,
      completed_count = EXCLUDED.completed_count,
      updated_at = EXCLUDED.updated_at;

INSERT INTO twitch_streamers_v2(guild_id, streamer_login, created_at, updated_at)
SELECT guild_id, streamer_login, created_at, updated_at
  FROM twitch_streamers
ON CONFLICT (guild_id, streamer_login) DO UPDATE
  SET updated_at = EXCLUDED.updated_at;

INSERT INTO valorant_sent_bundles_v2(guild_id, bundle_uuid, notified_at)
SELECT guild_id, bundle_uuid, notified_at
  FROM valorant_sent_bundles
ON CONFLICT (guild_id, bundle_uuid) DO UPDATE
  SET notified_at = EXCLUDED.notified_at;

-- Economy.
INSERT INTO economy_profiles_v2(guild_id, member_id, balance, last_daily_claim, created_at, updated_at)
SELECT ep.guild_id, gm2.id, ep.balance, ep.last_daily_claim, ep.created_at, ep.updated_at
  FROM economy_profiles ep
  JOIN guild_members_v2 gm2
    ON gm2.guild_id = ep.guild_id
   AND gm2.legacy_user_id = ep.user_id
ON CONFLICT (guild_id, member_id) DO UPDATE
  SET balance = EXCLUDED.balance,
      last_daily_claim = EXCLUDED.last_daily_claim,
      updated_at = EXCLUDED.updated_at;

INSERT INTO economy_inventory_items_v2(guild_id, member_id, item_name, quantity, created_at, updated_at)
SELECT ei.guild_id, gm2.id, ei.item_name, ei.quantity, ei.created_at, ei.updated_at
  FROM economy_inventory_items ei
  JOIN guild_members_v2 gm2
    ON gm2.guild_id = ei.guild_id
   AND gm2.legacy_user_id = ei.user_id
ON CONFLICT (guild_id, member_id, item_name) DO UPDATE
  SET quantity = EXCLUDED.quantity,
      updated_at = EXCLUDED.updated_at;

-- Reputation and user profiles.
INSERT INTO user_profiles_v2(discord_user_id, genre, valorant_tracker, lft, note, created_at, updated_at)
SELECT du.id, up.genre, up.valorant_tracker, up.lft, up.note, up.created_at, up.updated_at
  FROM user_profiles up
  JOIN discord_users_v2 du ON du.legacy_user_id = up.user_id
ON CONFLICT (discord_user_id) DO UPDATE
  SET genre = EXCLUDED.genre,
      valorant_tracker = EXCLUDED.valorant_tracker,
      lft = EXCLUDED.lft,
      note = EXCLUDED.note,
      updated_at = EXCLUDED.updated_at;

INSERT INTO reputation_events_v2(
  guild_id,
  reporter_member_id,
  target_member_id,
  event_type,
  event_date,
  count,
  reason,
  created_at,
  updated_at
)
SELECT
  re.guild_id,
  reporter.id,
  target.id,
  re.event_type,
  re.event_date,
  re.count,
  re.reason,
  re.created_at,
  re.updated_at
FROM reputation_events re
JOIN guild_members_v2 reporter
  ON reporter.guild_id = re.guild_id
 AND reporter.legacy_user_id = re.reporter_user_id
JOIN guild_members_v2 target
  ON target.guild_id = re.guild_id
 AND target.legacy_user_id = re.target_user_id
WHERE re.event_type IN ('report', 'recommendation')
ON CONFLICT (guild_id, reporter_member_id, target_member_id, event_type, event_date)
  DO UPDATE SET count = EXCLUDED.count,
                reason = EXCLUDED.reason,
                updated_at = EXCLUDED.updated_at;

-- Message deletion history.
INSERT INTO message_deletions_v2(
  id,
  guild_id,
  deleted_by_member_id,
  source,
  channel_id,
  channel_name,
  deletion_type,
  target_user_id,
  target_user_tag,
  message_count,
  created_at
)
SELECT
  md.id::BIGINT,
  md.guild_id,
  moderator.id,
  md.source,
  md.channel_id,
  md.channel_name,
  md.deletion_type,
  target_user.id,
  md.target_user_tag,
  md.message_count,
  md.created_at
FROM message_deletions md
LEFT JOIN guild_members_v2 moderator
  ON moderator.guild_id = md.guild_id
 AND moderator.legacy_user_id = md.deleted_by_user_id
LEFT JOIN users target_legacy
  ON target_legacy.user_id = md.target_user_id
LEFT JOIN discord_users_v2 target_user
  ON target_user.discord_id = target_legacy.discord_id
ON CONFLICT (id) DO UPDATE
  SET deleted_by_member_id = EXCLUDED.deleted_by_member_id,
      source = EXCLUDED.source,
      channel_id = EXCLUDED.channel_id,
      channel_name = EXCLUDED.channel_name,
      deletion_type = EXCLUDED.deletion_type,
      target_user_id = EXCLUDED.target_user_id,
      target_user_tag = EXCLUDED.target_user_tag,
      message_count = EXCLUDED.message_count,
      created_at = EXCLUDED.created_at;

SELECT setval(
  pg_get_serial_sequence('message_deletions_v2', 'id'),
  GREATEST((SELECT COALESCE(MAX(id), 1) FROM message_deletions_v2), 1),
  TRUE
);
