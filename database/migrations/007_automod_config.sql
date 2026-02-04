-- 007_automod_config.sql
-- Configuration de l'auto-modération par serveur.

CREATE TABLE IF NOT EXISTS automod_config (
    guild_id BIGINT PRIMARY KEY REFERENCES guilds(guild_id) ON DELETE CASCADE,
    scam_detection_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    spam_detection_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    spam_channel_threshold INT NOT NULL DEFAULT 3 CHECK (spam_channel_threshold > 0),
    spam_time_window INT NOT NULL DEFAULT 60 CHECK (spam_time_window > 0),
    delete_messages_on_scam BOOLEAN NOT NULL DEFAULT TRUE,
    delete_period_hours INT NOT NULL DEFAULT 24 CHECK (delete_period_hours > 0),
    whitelisted_roles BIGINT[] NOT NULL DEFAULT '{}',
    whitelisted_channels BIGINT[] NOT NULL DEFAULT '{}',
    custom_scam_patterns TEXT[] NOT NULL DEFAULT '{}',
    custom_scam_domains TEXT[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
