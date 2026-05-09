-- Scrims active domain.
--
-- Legacy scrims used serveur_id/user_id internal ids directly and stored
-- message state in the same table. Keep a backup, then create the current
-- multi-guild table with explicit status and user arrays.

DO $$
BEGIN
  IF to_regclass('public.scrims') IS NOT NULL
     AND NOT EXISTS (
       SELECT 1
         FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'scrims'
          AND column_name = 'scheduled_at'
     )
  THEN
    CREATE TABLE IF NOT EXISTS scrims_legacy_backup AS TABLE scrims WITH DATA;
    IF to_regclass('public.scrims_legacy_pre_020') IS NULL THEN
      ALTER TABLE scrims RENAME TO scrims_legacy_pre_020;
    ELSE
      EXECUTE format(
        'ALTER TABLE scrims RENAME TO %I',
        'scrims_legacy_pre_020_' || floor(extract(epoch from clock_timestamp()))::bigint
      );
    END IF;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS scrims (
  id              BIGSERIAL PRIMARY KEY,
  guild_id        BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  creator_user_id BIGINT NULL REFERENCES users(user_id) ON DELETE SET NULL,
  scheduled_at    TIMESTAMPTZ NOT NULL,
  map_name        TEXT NOT NULL,
  rank_name       TEXT NOT NULL,
  notes           TEXT NULL,
  team1_user_ids  BIGINT[] NOT NULL DEFAULT '{}',
  team2_user_ids  BIGINT[] NOT NULL DEFAULT '{}',
  channel_id      BIGINT NULL,
  message_id      BIGINT NULL,
  status          TEXT NOT NULL DEFAULT 'active',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  ended_at        TIMESTAMPTZ NULL,
  CHECK (status IN ('active', 'completed', 'cancelled')),
  CHECK (length(btrim(map_name)) > 0),
  CHECK (length(btrim(rank_name)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_scrims_guild_status
  ON scrims(guild_id, status);

CREATE INDEX IF NOT EXISTS idx_scrims_due
  ON scrims(status, scheduled_at);

CREATE INDEX IF NOT EXISTS idx_scrims_message_id
  ON scrims(message_id);

DO $$
BEGIN
  IF to_regclass('public.scrims_legacy_pre_020') IS NOT NULL
     AND to_regclass('public.serveur_id') IS NOT NULL
  THEN
    INSERT INTO scrims (
      id,
      guild_id,
      creator_user_id,
      scheduled_at,
      map_name,
      rank_name,
      notes,
      team1_user_ids,
      team2_user_ids,
      channel_id,
      message_id,
      status,
      created_at
    )
    SELECT
      legacy.id::BIGINT,
      s.guild_id,
      COALESCE((legacy.team1)[1]::BIGINT, (legacy.team2)[1]::BIGINT),
      legacy.datetime,
      legacy.map,
      legacy.rang,
      legacy.autre,
      ARRAY(
        SELECT value::BIGINT
          FROM unnest(COALESCE(legacy.team1, ARRAY[]::INTEGER[])) AS value
      ),
      ARRAY(
        SELECT value::BIGINT
          FROM unnest(COALESCE(legacy.team2, ARRAY[]::INTEGER[])) AS value
      ),
      legacy.channel_id,
      NULLIF(legacy.message_id, 0),
      CASE WHEN legacy.message_id <> 0 THEN 'active' ELSE 'cancelled' END,
      now()
      FROM scrims_legacy_pre_020 legacy
      JOIN serveur_id s ON s.id = legacy.guild_id
     WHERE s.guild_id IS NOT NULL
    ON CONFLICT (id) DO NOTHING;

    PERFORM setval(
      pg_get_serial_sequence('scrims', 'id'),
      GREATEST((SELECT COALESCE(MAX(id), 1) FROM scrims), 1),
      TRUE
    );
  END IF;
END $$;
