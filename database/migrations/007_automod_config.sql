-- 007_automod_config.sql
-- Configuration de l'auto-modération par serveur.

DO $$
BEGIN
  IF to_regclass('public.automod_config') IS NOT NULL
     AND NOT EXISTS (
       SELECT 1
         FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'automod_config'
          AND column_name = 'guild_id'
     )
  THEN
    EXECUTE 'CREATE TABLE IF NOT EXISTS automod_config_legacy_backup AS TABLE automod_config WITH DATA';
    IF to_regclass('public.automod_config_legacy_pre_007') IS NULL THEN
      ALTER TABLE automod_config RENAME TO automod_config_legacy_pre_007;
    ELSE
      DROP TABLE automod_config;
    END IF;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS automod_config (
    guild_id BIGINT PRIMARY KEY REFERENCES guilds(guild_id) ON DELETE CASCADE,
    scam_detection_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    spam_detection_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    spam_channel_threshold INT NOT NULL DEFAULT 3 CHECK (spam_channel_threshold > 0),
    spam_time_window INT NOT NULL DEFAULT 60 CHECK (spam_time_window > 0),
    delete_messages_on_scam BOOLEAN NOT NULL DEFAULT TRUE,
    delete_period_hours INT NOT NULL DEFAULT 24 CHECK (delete_period_hours > 0),
    whitelisted_roles BIGINT[] NOT NULL DEFAULT '{}',
    whitelisted_channels BIGINT[] NOT NULL DEFAULT '{}',
    custom_scam_patterns TEXT[] NOT NULL DEFAULT '{}',
    custom_scam_domains TEXT[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$
BEGIN
  IF to_regclass('public.automod_config_legacy_pre_007') IS NOT NULL
     AND to_regclass('public.serveur_id') IS NOT NULL
  THEN
    INSERT INTO automod_config(
      guild_id,
      scam_detection_enabled,
      spam_detection_enabled,
      spam_channel_threshold,
      spam_time_window,
      delete_messages_on_scam,
      delete_period_hours,
      whitelisted_roles,
      whitelisted_channels,
      custom_scam_patterns,
      custom_scam_domains,
      created_at,
      updated_at
    )
    SELECT
      s.guild_id,
      COALESCE(a.scam_detection_enabled, TRUE),
      COALESCE(a.spam_detection_enabled, TRUE),
      COALESCE(a.spam_channel_threshold, 3),
      COALESCE(a.spam_time_window, 60),
      COALESCE(a.delete_messages_on_scam, TRUE),
      COALESCE(a.delete_period_hours, 24),
      COALESCE(a.whitelisted_roles, '{}'),
      COALESCE(a.whitelisted_channels, '{}'),
      COALESCE(a.custom_scam_patterns, '{}'),
      COALESCE(a.custom_scam_domains, '{}'),
      COALESCE(a.created_at::TIMESTAMPTZ, now()),
      COALESCE(a.updated_at::TIMESTAMPTZ, now())
    FROM automod_config_legacy_pre_007 a
    JOIN serveur_id s ON s.id = a.server_id
    WHERE s.guild_id IS NOT NULL
    ON CONFLICT (guild_id) DO UPDATE SET
      scam_detection_enabled = EXCLUDED.scam_detection_enabled,
      spam_detection_enabled = EXCLUDED.spam_detection_enabled,
      spam_channel_threshold = EXCLUDED.spam_channel_threshold,
      spam_time_window = EXCLUDED.spam_time_window,
      delete_messages_on_scam = EXCLUDED.delete_messages_on_scam,
      delete_period_hours = EXCLUDED.delete_period_hours,
      whitelisted_roles = EXCLUDED.whitelisted_roles,
      whitelisted_channels = EXCLUDED.whitelisted_channels,
      custom_scam_patterns = EXCLUDED.custom_scam_patterns,
      custom_scam_domains = EXCLUDED.custom_scam_domains,
      updated_at = now();
  END IF;
END $$;
