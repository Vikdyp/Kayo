-- 015_reputation.sql
-- Tables pour le système de réputation et profils utilisateur

CREATE TABLE IF NOT EXISTS reputation_events (
    id          BIGSERIAL PRIMARY KEY,
    guild_id    BIGINT NOT NULL REFERENCES guilds(guild_id),
    reporter_discord_id BIGINT NOT NULL,
    target_discord_id   BIGINT NOT NULL,
    event_type  TEXT NOT NULL CHECK (event_type IN ('report', 'recommendation')),
    event_date  DATE NOT NULL DEFAULT CURRENT_DATE,
    UNIQUE (guild_id, reporter_discord_id, target_discord_id, event_type, event_date)
);

CREATE INDEX IF NOT EXISTS idx_reputation_target
    ON reputation_events (guild_id, target_discord_id, event_type);

CREATE TABLE IF NOT EXISTS user_profiles (
    discord_user_id BIGINT PRIMARY KEY,
    genre           TEXT,
    valorant_tracker TEXT,
    lft             TEXT,
    note            TEXT
);
