-- 005_persistent_messages.sql
-- Messages Discord persistants (récupérés au redémarrage)

DO $$
BEGIN
  IF to_regclass('public.persistent_messages') IS NOT NULL
     AND NOT EXISTS (
       SELECT 1
         FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'persistent_messages'
          AND column_name = 'guild_id'
     )
  THEN
    EXECUTE 'CREATE TABLE IF NOT EXISTS persistent_messages_legacy_backup AS TABLE persistent_messages WITH DATA';
    IF to_regclass('public.persistent_messages_legacy_pre_005') IS NULL THEN
      ALTER TABLE persistent_messages RENAME TO persistent_messages_legacy_pre_005;
    ELSE
      DROP TABLE persistent_messages;
    END IF;
  END IF;
END $$;

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

DO $$
BEGIN
  IF to_regclass('public.persistent_messages_legacy_pre_005') IS NOT NULL
     AND to_regclass('public.serveur_id') IS NOT NULL
  THEN
    INSERT INTO persistent_messages(
      guild_id,
      message_type,
      channel_id,
      message_id,
      created_at,
      updated_at
    )
    SELECT
      s.guild_id,
      pm.message_type,
      pm.channel_id,
      pm.message_id,
      COALESCE(pm.created_at::TIMESTAMPTZ, now()),
      now()
    FROM persistent_messages_legacy_pre_005 pm
    JOIN serveur_id s ON s.id = pm.server_id
    WHERE s.guild_id IS NOT NULL
      AND pm.message_type IS NOT NULL
      AND pm.channel_id IS NOT NULL
      AND pm.message_id IS NOT NULL
    ON CONFLICT (guild_id, message_type) DO UPDATE
      SET channel_id = EXCLUDED.channel_id,
          message_id = EXCLUDED.message_id,
          updated_at = now();
  END IF;
END $$;
