-- 012_streamer_partners.sql
-- Twitch streamers to monitor per guild.

CREATE TABLE IF NOT EXISTS streamer_partners (
  guild_id       BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  streamer_name  TEXT   NOT NULL,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (guild_id, streamer_name)
);
