-- 001_init.sql
-- Base configuration tables for Discord guild/channel/role mapping.

CREATE TABLE IF NOT EXISTS guilds (
  guild_id   BIGINT PRIMARY KEY,
  name_cache TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Channels mapped by human key per guild.
CREATE TABLE IF NOT EXISTS guild_channels (
  guild_id    BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  key         TEXT   NOT NULL,
  channel_id  BIGINT NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (guild_id, key)
);

-- Roles mapped by human key per guild.
CREATE TABLE IF NOT EXISTS guild_roles (
  guild_id    BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  key         TEXT   NOT NULL,
  role_id     BIGINT NOT NULL,
  name_cache  TEXT   NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (guild_id, key)
);

-- Minimal sanity constraints: non-empty keys, bounded length.
ALTER TABLE guild_channels
  ADD CONSTRAINT guild_channels_key_nonempty
  CHECK (length(btrim(key)) > 0 AND length(key) <= 100);

ALTER TABLE guild_roles
  ADD CONSTRAINT guild_roles_key_nonempty
  CHECK (length(btrim(key)) > 0 AND length(key) <= 100);

-- Helpful indexes for reverse lookups / audits.
CREATE INDEX IF NOT EXISTS idx_guild_channels_channel_id
  ON guild_channels(channel_id);

CREATE INDEX IF NOT EXISTS idx_guild_roles_role_id
  ON guild_roles(role_id);

-- Optional: speed up "all configs for guild" queries (Postgres can use PK for many cases,
-- but this helps when filtering by guild_id only with large tables).
CREATE INDEX IF NOT EXISTS idx_guild_channels_guild_id
  ON guild_channels(guild_id);

CREATE INDEX IF NOT EXISTS idx_guild_roles_guild_id
  ON guild_roles(guild_id);
