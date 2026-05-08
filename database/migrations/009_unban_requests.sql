-- 009_unban_requests.sql
-- Demandes de déban individuelles (séparées de persistent_messages)

CREATE TABLE IF NOT EXISTS unban_requests (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
    requester_user_id BIGINT NOT NULL REFERENCES users(user_id),
    channel_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL UNIQUE,
    reason TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ,
    resolved_by_user_id BIGINT REFERENCES users(user_id)
);

-- Index partiel : un seul pending par user/guild (permet l'historique accepted/rejected)
CREATE UNIQUE INDEX IF NOT EXISTS idx_unban_requests_one_pending_per_user
    ON unban_requests(guild_id, requester_user_id) WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_unban_requests_guild_status
    ON unban_requests(guild_id, status);

CREATE INDEX IF NOT EXISTS idx_unban_requests_message_id
    ON unban_requests(message_id);
