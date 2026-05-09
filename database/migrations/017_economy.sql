-- 017_economy.sql
-- Additive economy tables for per-guild balances and inventories.

CREATE TABLE IF NOT EXISTS economy_profiles (
  guild_id         BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  user_id          BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  balance          INTEGER NOT NULL DEFAULT 0 CHECK (balance >= 0),
  last_daily_claim DATE NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (guild_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_economy_profiles_user_id
  ON economy_profiles(user_id);

CREATE TABLE IF NOT EXISTS economy_inventory_items (
  guild_id   BIGINT NOT NULL,
  user_id    BIGINT NOT NULL,
  item_name  TEXT NOT NULL,
  quantity   INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (guild_id, user_id, item_name),
  FOREIGN KEY (guild_id, user_id)
    REFERENCES economy_profiles(guild_id, user_id)
    ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_economy_inventory_user_id
  ON economy_inventory_items(user_id);
