-- 006_message_deletions.sql
-- Historique des suppressions de messages (modérateurs et automod).

CREATE TABLE IF NOT EXISTS message_deletions (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
    deleted_by_user_id BIGINT REFERENCES users(user_id),  -- NULL si suppression automatique
    source TEXT NOT NULL DEFAULT 'moderator',  -- 'moderator', 'automod', 'system'
    channel_id BIGINT NOT NULL,
    channel_name TEXT,  -- snapshot pour historique visuel
    deletion_type TEXT NOT NULL,  -- all, user, number, from, image, gif, links, scam, spam...
    target_user_id BIGINT REFERENCES users(user_id),
    target_user_tag TEXT,  -- snapshot pour historique visuel
    message_count INT NOT NULL CHECK (message_count > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_message_deletions_guild_id
    ON message_deletions(guild_id);

CREATE INDEX IF NOT EXISTS idx_message_deletions_created_at
    ON message_deletions(created_at DESC);
