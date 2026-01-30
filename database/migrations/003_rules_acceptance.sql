-- 003_rules_acceptance.sql
-- Track whether a member accepted the rules (no versioning).

ALTER TABLE guild_members
  ADD COLUMN IF NOT EXISTS accepted_rules BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE guild_members
  ADD COLUMN IF NOT EXISTS accepted_rules_at TIMESTAMPTZ NULL;

-- Coherence: if accepted_rules is true, accepted_rules_at must be set
ALTER TABLE guild_members
  ADD CONSTRAINT guild_members_rules_acceptance_chk
  CHECK (
    (accepted_rules = FALSE AND accepted_rules_at IS NULL)
    OR
    (accepted_rules = TRUE  AND accepted_rules_at IS NOT NULL)
  );

-- Useful index for "who hasn't accepted" queries
CREATE INDEX IF NOT EXISTS idx_guild_members_rules_acceptance
  ON guild_members(guild_id, accepted_rules);
