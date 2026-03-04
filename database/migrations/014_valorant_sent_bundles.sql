-- 014_valorant_sent_bundles.sql
-- Tracks which Valorant shop bundles have already been notified.

CREATE TABLE IF NOT EXISTS valorant_sent_bundles (
  bundle_uuid  TEXT PRIMARY KEY,
  notified_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
