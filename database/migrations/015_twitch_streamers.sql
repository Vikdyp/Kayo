-- 015_twitch_streamers.sql
-- Reactivate Twitch notifications with current guild IDs.
-- Keep the legacy streamer_partners table as a backup and copy rows that can
-- be mapped from serveur_id to guilds.

DO $$
BEGIN
  IF to_regclass('public.streamer_partners') IS NOT NULL
     AND to_regclass('public.streamer_partners_legacy_backup_015') IS NULL
     AND EXISTS (
       SELECT 1
         FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'streamer_partners'
          AND column_name = 'server_id'
     )
  THEN
    ALTER TABLE public.streamer_partners RENAME TO streamer_partners_legacy_backup_015;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS twitch_streamers (
  guild_id       BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  streamer_login TEXT NOT NULL,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (guild_id, streamer_login),
  CHECK (streamer_login = lower(streamer_login)),
  CHECK (streamer_login ~ '^[a-z0-9_]{3,25}$')
);

DO $$
BEGIN
  IF to_regclass('public.serveur_id') IS NOT NULL THEN
    INSERT INTO guilds (guild_id, name_cache)
    SELECT DISTINCT serveur_id.guild_id, serveur_id.serveur
      FROM serveur_id
     WHERE serveur_id.guild_id IS NOT NULL
    ON CONFLICT (guild_id) DO NOTHING;
  END IF;

  IF to_regclass('public.streamer_partners_legacy_backup_015') IS NOT NULL
     AND to_regclass('public.serveur_id') IS NOT NULL
  THEN
    INSERT INTO twitch_streamers (guild_id, streamer_login)
    SELECT DISTINCT serveur_id.guild_id, lower(trim(legacy.streamer_name))
      FROM streamer_partners_legacy_backup_015 legacy
      JOIN serveur_id ON serveur_id.id = legacy.server_id
     WHERE legacy.streamer_name IS NOT NULL
       AND lower(trim(legacy.streamer_name)) ~ '^[a-z0-9_]{3,25}$'
    ON CONFLICT (guild_id, streamer_login) DO NOTHING;
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_twitch_streamers_guild_id
  ON twitch_streamers (guild_id);
