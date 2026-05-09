-- 018_tournaments.sql
-- Additive tournament tables with forward-only preservation of registrations.

DO $$
BEGIN
  IF to_regclass('public.tournaments') IS NOT NULL
     AND NOT EXISTS (
       SELECT 1
         FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'tournaments'
          AND column_name = 'guild_id'
     )
  THEN
    CREATE TABLE IF NOT EXISTS tournaments_legacy_backup AS TABLE tournaments WITH DATA;
    IF to_regclass('public.tournaments_legacy_pre_018') IS NULL THEN
      ALTER TABLE tournaments RENAME TO tournaments_legacy_pre_018;
    ELSE
      EXECUTE format(
        'ALTER TABLE tournaments RENAME TO %I',
        'tournaments_legacy_pre_018_' || floor(extract(epoch from clock_timestamp()))::bigint
      );
    END IF;
  END IF;

  IF to_regclass('public.team_registrations') IS NOT NULL
     AND NOT EXISTS (
       SELECT 1
         FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'team_registrations'
          AND column_name = 'guild_id'
     )
  THEN
    CREATE TABLE IF NOT EXISTS team_registrations_legacy_backup AS TABLE team_registrations WITH DATA;
    IF to_regclass('public.team_registrations_legacy_pre_018') IS NULL THEN
      ALTER TABLE team_registrations RENAME TO team_registrations_legacy_pre_018;
    ELSE
      EXECUTE format(
        'ALTER TABLE team_registrations RENAME TO %I',
        'team_registrations_legacy_pre_018_' || floor(extract(epoch from clock_timestamp()))::bigint
      );
    END IF;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS tournaments (
  id                      BIGSERIAL PRIMARY KEY,
  guild_id                BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  tournament_name         TEXT NOT NULL,
  max_teams               INTEGER NOT NULL CHECK (max_teams > 0),
  registration_start      TIMESTAMPTZ NOT NULL,
  registration_end        TIMESTAMPTZ NOT NULL,
  tournament_date         TIMESTAMPTZ NOT NULL,
  status                  TEXT NOT NULL DEFAULT 'active',
  registration_channel_id BIGINT NULL,
  registration_message_id BIGINT NULL,
  created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  closed_at               TIMESTAMPTZ NULL,
  CHECK (status IN ('active', 'closed')),
  CHECK (registration_end >= registration_start)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_tournaments_one_active_per_guild
  ON tournaments(guild_id)
  WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_tournaments_guild_status
  ON tournaments(guild_id, status);

CREATE TABLE IF NOT EXISTS tournament_teams (
  id                      BIGSERIAL PRIMARY KEY,
  tournament_id           BIGINT NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
  guild_id                BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  captain_user_id         BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  team_name               TEXT NOT NULL,
  player_discord_ids      BIGINT[] NOT NULL,
  substitute_discord_ids  BIGINT[] NOT NULL DEFAULT '{}',
  coach_discord_id        BIGINT NULL,
  created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tournament_id, team_name),
  CHECK (array_length(player_discord_ids, 1) = 5),
  CHECK (array_length(substitute_discord_ids, 1) IS NULL OR array_length(substitute_discord_ids, 1) <= 2)
);

CREATE INDEX IF NOT EXISTS idx_tournament_teams_tournament_id
  ON tournament_teams(tournament_id);

CREATE INDEX IF NOT EXISTS idx_tournament_teams_guild_id
  ON tournament_teams(guild_id);

DO $$
BEGIN
  IF to_regclass('public.tournaments_legacy_pre_018') IS NOT NULL
     AND to_regclass('public.serveur_id') IS NOT NULL
  THEN
    INSERT INTO tournaments (
      id, guild_id, tournament_name, max_teams, registration_start,
      registration_end, tournament_date, status, created_at
    )
    SELECT t.id::BIGINT,
           s.guild_id,
           t.tournament_name,
           t.max_teams,
           t.registration_start,
           t.registration_end,
           t.tournament_date,
           CASE WHEN t.status IN ('active', 'closed') THEN t.status ELSE 'closed' END,
           COALESCE(t.created_at, now())
      FROM tournaments_legacy_pre_018 t
      JOIN serveur_id s ON s.id = t.server_id
     WHERE s.guild_id IS NOT NULL
    ON CONFLICT (id) DO NOTHING;

    PERFORM setval(
      pg_get_serial_sequence('tournaments', 'id'),
      GREATEST((SELECT COALESCE(MAX(id), 1) FROM tournaments), 1),
      TRUE
    );
  END IF;
END $$;
