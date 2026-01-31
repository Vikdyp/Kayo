-- 005_persistent_messages.sql
-- Messages Discord persistants (récupérés au redémarrage)

CREATE TABLE IF NOT EXISTS persistent_messages (
    guild_id     BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
    message_type TEXT NOT NULL CHECK (length(btrim(message_type)) > 0 AND length(message_type) <= 100),
    channel_id   BIGINT NOT NULL,
    message_id   BIGINT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, message_type)
);

-- Index pour recherche par message_id (vérification existence)
CREATE INDEX IF NOT EXISTS idx_persistent_messages_message_id
    ON persistent_messages(message_id);
