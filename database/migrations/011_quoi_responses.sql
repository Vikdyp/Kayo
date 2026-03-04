-- 011_quoi_responses.sql
-- Tracks how many times each user triggered the "quoicoubeh" responder.

CREATE TABLE IF NOT EXISTS quoi_responses (
  guild_id         BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  discord_user_id  BIGINT NOT NULL,
  trigger_count    INT    NOT NULL DEFAULT 0,
  last_triggered   TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (guild_id, discord_user_id)
);
