-- 016_role_combinations.sql
-- Reactivate role combinations with current guild IDs and Discord role IDs.
-- Legacy role_combinations stored roles_configurations.id values. Keep a
-- backup and copy rows through roles_configurations.role_id.

DO $$
BEGIN
  IF to_regclass('public.role_combinations') IS NOT NULL
     AND to_regclass('public.role_combinations_legacy_backup_016') IS NULL
     AND EXISTS (
       SELECT 1
         FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'role_combinations'
          AND column_name = 'server_id'
     )
  THEN
    ALTER TABLE public.role_combinations RENAME TO role_combinations_legacy_backup_016;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS role_combinations (
  id                BIGSERIAL PRIMARY KEY,
  guild_id          BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  primary_role_id   BIGINT NOT NULL,
  secondary_role_id BIGINT NOT NULL,
  combined_role_id  BIGINT NOT NULL,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (primary_role_id <> secondary_role_id),
  CHECK (combined_role_id <> primary_role_id),
  CHECK (combined_role_id <> secondary_role_id),
  UNIQUE (guild_id, primary_role_id, secondary_role_id)
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

  IF to_regclass('public.role_combinations_legacy_backup_016') IS NOT NULL
     AND to_regclass('public.roles_configurations') IS NOT NULL
  THEN
    INSERT INTO role_combinations (
      guild_id,
      primary_role_id,
      secondary_role_id,
      combined_role_id
    )
    SELECT
      legacy.guild_id,
      LEAST(primary_role.role_id, secondary_role.role_id),
      GREATEST(primary_role.role_id, secondary_role.role_id),
      combined_role.role_id
      FROM role_combinations_legacy_backup_016 legacy
      JOIN roles_configurations primary_role ON primary_role.id = legacy.primary_role_id
      JOIN roles_configurations secondary_role ON secondary_role.id = legacy.secondary_role_id
      JOIN roles_configurations combined_role ON combined_role.id = legacy.combined_role_id
     WHERE legacy.guild_id IS NOT NULL
       AND primary_role.role_id IS NOT NULL
       AND secondary_role.role_id IS NOT NULL
       AND combined_role.role_id IS NOT NULL
       AND primary_role.role_id <> secondary_role.role_id
       AND combined_role.role_id <> primary_role.role_id
       AND combined_role.role_id <> secondary_role.role_id
    ON CONFLICT (guild_id, primary_role_id, secondary_role_id) DO UPDATE
      SET combined_role_id = EXCLUDED.combined_role_id,
          updated_at = now();
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_role_combinations_guild_id
  ON role_combinations (guild_id);
