-- 008_moderation_bans.sql
-- Tables de modération: bans, warnings, role backups.

-- Bans actifs
CREATE TABLE IF NOT EXISTS moderation_bans (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(user_id),
    ban_type TEXT NOT NULL CHECK (ban_type IN ('temp', 'perm', 'soft')),
    reason TEXT,
    banned_by_user_id BIGINT NOT NULL REFERENCES users(user_id),
    banned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ban_end TIMESTAMPTZ,  -- NULL = permanent
    UNIQUE(guild_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_moderation_bans_ban_end
    ON moderation_bans(ban_end) WHERE ban_end IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_moderation_bans_guild_id
    ON moderation_bans(guild_id);


-- Warnings séparés (comptables dynamiquement)
CREATE TABLE IF NOT EXISTS moderation_warnings (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(user_id),
    warned_by_user_id BIGINT NOT NULL REFERENCES users(user_id),
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_moderation_warnings_guild_user
    ON moderation_warnings(guild_id, user_id);


-- Backup des rôles (séparé des bans)
CREATE TABLE IF NOT EXISTS moderation_role_backups (
    guild_id BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(user_id),
    roles BIGINT[] NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, user_id)
);
