-- 016_economy.sql
-- Tables pour le système économique

CREATE TABLE IF NOT EXISTS user_economy (
    discord_user_id BIGINT PRIMARY KEY,
    balance         INT NOT NULL DEFAULT 0,
    last_claim      TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS user_inventory (
    id              BIGSERIAL PRIMARY KEY,
    discord_user_id BIGINT NOT NULL REFERENCES user_economy(discord_user_id),
    item_name       TEXT NOT NULL,
    acquired_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_inventory_user
    ON user_inventory (discord_user_id);
