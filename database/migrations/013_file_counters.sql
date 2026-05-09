-- 013_file_counters.sql
-- Reactivate file counters with a guild_id contract based on Discord guild IDs.
-- Older deployments may already have file_counters.guild_id as an internal
-- serveur_id.id value with ajouter_count / terminer_count columns. Preserve it
-- by renaming it to a backup table and copying rows into the new schema.

DO $$
DECLARE
  has_legacy_table BOOLEAN;
BEGIN
  IF to_regclass('public.file_counters') IS NULL THEN
    RETURN;
  END IF;

  SELECT EXISTS (
    SELECT 1
      FROM information_schema.columns
     WHERE table_schema = 'public'
       AND table_name = 'file_counters'
       AND column_name IN ('ajouter_count', 'terminer_count')
  ) INTO has_legacy_table;

  IF has_legacy_table
     AND to_regclass('public.file_counters_legacy_backup_013') IS NULL
  THEN
    ALTER TABLE public.file_counters RENAME TO file_counters_legacy_backup_013;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS file_counters (
  guild_id        BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  channel_id      BIGINT NOT NULL,
  message_id      BIGINT NOT NULL,
  added_count     INTEGER NOT NULL DEFAULT 0,
  completed_count INTEGER NOT NULL DEFAULT 0,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (guild_id, channel_id)
);

DO $$
BEGIN
  IF to_regclass('public.serveur_id') IS NOT NULL
     AND to_regclass('public.file_counters_legacy_backup_013') IS NOT NULL
  THEN
    INSERT INTO guilds (guild_id, name_cache)
    SELECT DISTINCT serveur_id.guild_id, serveur_id.serveur
      FROM serveur_id
     WHERE serveur_id.guild_id IS NOT NULL
    ON CONFLICT (guild_id) DO NOTHING;

    INSERT INTO file_counters (
      guild_id,
      channel_id,
      message_id,
      added_count,
      completed_count
    )
    SELECT
      COALESCE(serveur_id.guild_id, legacy.guild_id::BIGINT),
      legacy.channel_id,
      legacy.message_id,
      legacy.ajouter_count,
      legacy.terminer_count
    FROM file_counters_legacy_backup_013 legacy
    LEFT JOIN serveur_id ON serveur_id.id = legacy.guild_id
    ON CONFLICT (guild_id, channel_id) DO UPDATE
      SET message_id = EXCLUDED.message_id,
          added_count = EXCLUDED.added_count,
          completed_count = EXCLUDED.completed_count,
          updated_at = now();
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_file_counters_message_id
  ON file_counters (message_id);
