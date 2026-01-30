-- 002_users_and_members.sql
-- Global users registry + per-guild membership tracking.

-- Global users table (internal id for heavy stats tables)
CREATE TABLE IF NOT EXISTS users (
  user_id      BIGSERIAL PRIMARY KEY,
  discord_id   BIGINT NOT NULL UNIQUE,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS idx_users_discord_id
  ON users(discord_id);


-- Membership per guild
CREATE TABLE IF NOT EXISTS guild_members (
  guild_id    BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  user_id     BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  is_member   BOOLEAN NOT NULL DEFAULT TRUE,
  joined_at   TIMESTAMPTZ NULL,
  left_at     TIMESTAMPTZ NULL,
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (guild_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_guild_members_user_id
  ON guild_members(user_id);

CREATE INDEX IF NOT EXISTS idx_guild_members_guild_active
  ON guild_members(guild_id, is_member);


-- Coherence: if user is active, left_at must be NULL
ALTER TABLE guild_members
  ADD CONSTRAINT guild_members_membership_state_chk
  CHECK (
    (is_member = TRUE  AND left_at IS NULL)
    OR
    (is_member = FALSE AND left_at IS NOT NULL)
  );
