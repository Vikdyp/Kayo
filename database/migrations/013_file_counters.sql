-- 013_file_counters.sql
-- Interactive file tracking counter per guild/channel.

CREATE TABLE IF NOT EXISTS file_counters (
  guild_id        BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  channel_id      BIGINT NOT NULL,
  message_id      BIGINT NOT NULL,
  ajouter_count   INT    NOT NULL DEFAULT 0,
  terminer_count  INT    NOT NULL DEFAULT 0,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (guild_id, channel_id)
);
