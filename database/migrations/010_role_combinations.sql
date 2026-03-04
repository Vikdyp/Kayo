-- 010_role_combinations.sql
-- Role combination rules: when a member gains both primary+secondary roles,
-- replace them with the combined role.

CREATE TABLE IF NOT EXISTS role_combinations (
  guild_id           BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  primary_role_id    BIGINT NOT NULL,
  secondary_role_id  BIGINT NOT NULL,
  combined_role_id   BIGINT NOT NULL,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (guild_id, primary_role_id, secondary_role_id)
);

CREATE INDEX IF NOT EXISTS idx_role_combinations_guild_id
  ON role_combinations(guild_id);
