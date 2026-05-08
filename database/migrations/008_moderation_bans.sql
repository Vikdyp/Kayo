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

DO $$
BEGIN
  IF to_regclass('public.bans') IS NOT NULL
     AND to_regclass('public.serveur_id') IS NOT NULL
  THEN
    INSERT INTO moderation_bans(
      guild_id,
      user_id,
      ban_type,
      reason,
      banned_by_user_id,
      banned_at,
      ban_end
    )
    SELECT
      s.guild_id,
      target.user_id,
      CASE
        WHEN lower(b.ban_type) IN ('temp', 'perm', 'soft') THEN lower(b.ban_type)
        WHEN b.ban_end IS NULL THEN 'perm'
        ELSE 'temp'
      END,
      b.ban_reason,
      moderator.user_id,
      b.banned_at::TIMESTAMPTZ,
      b.ban_end::TIMESTAMPTZ
    FROM bans b
    JOIN serveur_id s ON s.id = b.server_id
    JOIN users target ON target.user_id = b.user_id
    JOIN users moderator ON moderator.user_id = b.banned_by
    WHERE s.guild_id IS NOT NULL
    ON CONFLICT (guild_id, user_id) DO UPDATE SET
      ban_type = EXCLUDED.ban_type,
      reason = EXCLUDED.reason,
      banned_by_user_id = EXCLUDED.banned_by_user_id,
      banned_at = EXCLUDED.banned_at,
      ban_end = EXCLUDED.ban_end;

    INSERT INTO moderation_role_backups(guild_id, user_id, roles, created_at)
    SELECT
      s.guild_id,
      target.user_id,
      b.roles_backup,
      now()
    FROM bans b
    JOIN serveur_id s ON s.id = b.server_id
    JOIN users target ON target.user_id = b.user_id
    WHERE b.roles_backup IS NOT NULL
      AND s.guild_id IS NOT NULL
    ON CONFLICT (guild_id, user_id) DO UPDATE SET
      roles = EXCLUDED.roles,
      created_at = now();
  END IF;
END $$;
