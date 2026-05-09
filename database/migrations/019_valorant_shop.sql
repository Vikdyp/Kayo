-- Valorant shop notifications.
--
-- Older local/legacy code used a global valorant_sent_bundles table with no
-- guild_id. Preserve that data, then create the multi-guild table used by the
-- active service.

DO $$
BEGIN
    IF to_regclass('public.valorant_sent_bundles') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1
             FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'valorant_sent_bundles'
              AND column_name = 'guild_id'
       )
    THEN
        CREATE TABLE IF NOT EXISTS valorant_sent_bundles_legacy_backup AS
        SELECT *
          FROM valorant_sent_bundles;

        ALTER TABLE valorant_sent_bundles
        RENAME TO valorant_sent_bundles_legacy_pre_019;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS valorant_sent_bundles (
    guild_id BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
    bundle_uuid TEXT NOT NULL,
    notified_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, bundle_uuid)
);

DO $$
BEGIN
    IF to_regclass('public.valorant_sent_bundles_legacy_pre_019') IS NOT NULL THEN
        INSERT INTO valorant_sent_bundles (guild_id, bundle_uuid, notified_at)
        SELECT DISTINCT gc.guild_id, legacy.bundle_uuid, legacy.notified_at
          FROM guild_channels gc
         CROSS JOIN valorant_sent_bundles_legacy_pre_019 legacy
         WHERE gc.key = 'valorant_shop'
           AND legacy.bundle_uuid IS NOT NULL
        ON CONFLICT (guild_id, bundle_uuid) DO NOTHING;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_valorant_sent_bundles_guild_id
    ON valorant_sent_bundles(guild_id);
