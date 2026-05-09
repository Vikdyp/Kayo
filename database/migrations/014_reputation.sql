-- 014_reputation.sql
-- Reactivate reputation/profile with current guilds/users IDs.
-- Legacy tables used serveur_id.id and user_id.id. Keep backups and copy rows
-- that can be mapped to the current guilds/users tables.

DO $$
BEGIN
  IF to_regclass('public.reputation_events') IS NOT NULL
     AND to_regclass('public.reputation_events_legacy_backup_014') IS NULL
     AND EXISTS (
       SELECT 1
         FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'reputation_events'
          AND column_name = 'server_id'
     )
  THEN
    ALTER TABLE public.reputation_events RENAME TO reputation_events_legacy_backup_014;
  END IF;

  IF to_regclass('public.user_profile') IS NOT NULL
     AND to_regclass('public.user_profile_legacy_backup_014') IS NULL
  THEN
    ALTER TABLE public.user_profile RENAME TO user_profile_legacy_backup_014;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS reputation_events (
  id               BIGSERIAL PRIMARY KEY,
  guild_id         BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  reporter_user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  target_user_id   BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  event_type       TEXT NOT NULL CHECK (event_type IN ('report', 'recommendation')),
  event_date       DATE NOT NULL DEFAULT CURRENT_DATE,
  count            INTEGER NOT NULL DEFAULT 1 CHECK (count > 0),
  reason           TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (guild_id, reporter_user_id, target_user_id, event_type, event_date)
);

CREATE TABLE IF NOT EXISTS user_profiles (
  user_id          BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
  genre            TEXT,
  valorant_tracker TEXT,
  lft              TEXT,
  note             TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
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

  IF to_regclass('public.user_id') IS NOT NULL THEN
    INSERT INTO users (user_id, discord_id)
    SELECT legacy_users.id::BIGINT, legacy_users.discord_id
      FROM user_id legacy_users
     WHERE legacy_users.discord_id IS NOT NULL
    ON CONFLICT (discord_id) DO NOTHING;

    PERFORM setval(
      pg_get_serial_sequence('users', 'user_id'),
      GREATEST((SELECT COALESCE(MAX(user_id), 1) FROM users), 1),
      TRUE
    );
  END IF;

  IF to_regclass('public.reputation_events_legacy_backup_014') IS NOT NULL
     AND to_regclass('public.serveur_id') IS NOT NULL
  THEN
    INSERT INTO reputation_events (
      guild_id,
      reporter_user_id,
      target_user_id,
      event_type,
      event_date,
      count
    )
    SELECT
      serveur_id.guild_id,
      legacy.reporter_id::BIGINT,
      legacy.target_id::BIGINT,
      CASE
        WHEN legacy.event_type = 'recommend' THEN 'recommendation'
        ELSE legacy.event_type
      END,
      legacy.event_date,
      GREATEST(legacy.count, 1)
    FROM reputation_events_legacy_backup_014 legacy
    JOIN serveur_id ON serveur_id.id = legacy.server_id
    JOIN users reporter ON reporter.user_id = legacy.reporter_id::BIGINT
    JOIN users target_user ON target_user.user_id = legacy.target_id::BIGINT
    WHERE legacy.event_type IN ('report', 'recommendation', 'recommend')
    ON CONFLICT (guild_id, reporter_user_id, target_user_id, event_type, event_date)
      DO UPDATE SET count = GREATEST(reputation_events.count, EXCLUDED.count),
                    updated_at = now();
  END IF;

  IF to_regclass('public.user_profile_legacy_backup_014') IS NOT NULL THEN
    INSERT INTO user_profiles (user_id, genre, valorant_tracker, lft, note)
    SELECT
      legacy.user_id::BIGINT,
      legacy.genre,
      legacy.valorant_tracker,
      legacy.lft,
      legacy.note
    FROM user_profile_legacy_backup_014 legacy
    JOIN users ON users.user_id = legacy.user_id::BIGINT
    WHERE legacy.user_id IS NOT NULL
    ON CONFLICT (user_id) DO UPDATE
      SET genre = EXCLUDED.genre,
          valorant_tracker = EXCLUDED.valorant_tracker,
          lft = EXCLUDED.lft,
          note = EXCLUDED.note,
          updated_at = now();
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_reputation_events_target
  ON reputation_events (guild_id, target_user_id, event_type);

CREATE INDEX IF NOT EXISTS idx_reputation_events_reporter_target
  ON reputation_events (guild_id, reporter_user_id, target_user_id, event_type);
