-- 022_identity_v2.sql
-- Non-destructive identity v2 foundation.
--
-- The existing users/guild_members tables remain authoritative for runtime.
-- These v2 tables are backfilled from current data so repositories can migrate
-- domain by domain without losing data.

CREATE TABLE IF NOT EXISTS discord_users_v2 (
  id             BIGSERIAL PRIMARY KEY,
  discord_id     BIGINT NOT NULL UNIQUE,
  legacy_user_id BIGINT UNIQUE REFERENCES users(user_id) ON DELETE SET NULL,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at   TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS idx_discord_users_v2_discord_id
  ON discord_users_v2(discord_id);

CREATE INDEX IF NOT EXISTS idx_discord_users_v2_legacy_user_id
  ON discord_users_v2(legacy_user_id);

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

CREATE TABLE IF NOT EXISTS guild_members_v2 (
  id                 BIGSERIAL PRIMARY KEY,
  guild_id           BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  discord_user_id    BIGINT NOT NULL REFERENCES discord_users_v2(id) ON DELETE CASCADE,
  legacy_user_id     BIGINT NULL REFERENCES users(user_id) ON DELETE SET NULL,
  is_member          BOOLEAN NOT NULL DEFAULT TRUE,
  joined_at          TIMESTAMPTZ NULL,
  left_at            TIMESTAMPTZ NULL,
  accepted_rules     BOOLEAN NOT NULL DEFAULT FALSE,
  accepted_rules_at  TIMESTAMPTZ NULL,
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (guild_id, discord_user_id)
);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
      FROM pg_constraint
     WHERE conname = 'guild_members_v2_membership_state_chk'
       AND conrelid = 'public.guild_members_v2'::regclass
  ) THEN
    ALTER TABLE guild_members_v2
      ADD CONSTRAINT guild_members_v2_membership_state_chk
      CHECK (
        (is_member = TRUE  AND left_at IS NULL)
        OR
        (is_member = FALSE AND left_at IS NOT NULL)
      );
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_guild_members_v2_guild_active
  ON guild_members_v2(guild_id, is_member);

CREATE INDEX IF NOT EXISTS idx_guild_members_v2_discord_user_id
  ON guild_members_v2(discord_user_id);

CREATE INDEX IF NOT EXISTS idx_guild_members_v2_legacy_user_id
  ON guild_members_v2(legacy_user_id);

CREATE INDEX IF NOT EXISTS idx_guild_members_v2_rules_acceptance
  ON guild_members_v2(guild_id, accepted_rules);

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
