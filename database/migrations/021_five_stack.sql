-- Five-stack matchmaking domain.
--
-- Legacy tables (`teams`, `team_members`, `matchmaking_queue`, ... when
-- present) are preserved. The active runtime uses explicit `five_stack_*`
-- tables keyed by Discord guild_id.

CREATE TABLE IF NOT EXISTS five_stack_teams (
  code             TEXT NOT NULL,
  guild_id         BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  leader_discord_id BIGINT NOT NULL,
  visibility       TEXT NOT NULL DEFAULT 'public',
  forum_channel_id BIGINT NULL,
  thread_id        BIGINT NULL,
  voice_channel_id BIGINT NULL,
  status           TEXT NOT NULL DEFAULT 'active',
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (guild_id, code),
  CHECK (visibility IN ('public', 'private')),
  CHECK (status IN ('active', 'deleted'))
);

CREATE INDEX IF NOT EXISTS idx_five_stack_teams_guild_status
  ON five_stack_teams(guild_id, status);

CREATE TABLE IF NOT EXISTS five_stack_team_members (
  guild_id          BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  team_code         TEXT NOT NULL,
  member_discord_id BIGINT NOT NULL,
  joined_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (guild_id, team_code, member_discord_id),
  FOREIGN KEY (guild_id, team_code)
    REFERENCES five_stack_teams(guild_id, code) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_five_stack_team_members_member
  ON five_stack_team_members(guild_id, member_discord_id);

CREATE TABLE IF NOT EXISTS five_stack_queue (
  id                BIGSERIAL PRIMARY KEY,
  guild_id          BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  discord_member_id BIGINT NOT NULL,
  entry_type        INTEGER NOT NULL CHECK (entry_type BETWEEN 1 AND 5),
  team_code         TEXT NULL,
  team_member_ids   BIGINT[] NOT NULL DEFAULT '{}',
  language          TEXT NOT NULL DEFAULT 'francais',
  region            TEXT NOT NULL DEFAULT 'eu',
  platform          TEXT NOT NULL DEFAULT 'pc',
  desired_team_size INTEGER NOT NULL DEFAULT 0 CHECK (desired_team_size IN (0, 2, 3, 5)),
  mmr_extended      BOOLEAN NOT NULL DEFAULT FALSE,
  elo               INTEGER NULL,
  elo_high          INTEGER NULL,
  elo_low           INTEGER NULL,
  roles             TEXT[] NOT NULL DEFAULT '{}',
  queued_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (guild_id, discord_member_id)
);

CREATE INDEX IF NOT EXISTS idx_five_stack_queue_guild
  ON five_stack_queue(guild_id, queued_at);

CREATE TABLE IF NOT EXISTS five_stack_matches (
  id                      BIGSERIAL PRIMARY KEY,
  guild_id                BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  match_code              TEXT NOT NULL,
  voice_channel_id        BIGINT NULL,
  quality_score           DOUBLE PRECISION NOT NULL DEFAULT 0,
  elo_spread              INTEGER NOT NULL DEFAULT 0,
  avg_elo                 INTEGER NOT NULL DEFAULT 0,
  role_diversity_score    DOUBLE PRECISION NOT NULL DEFAULT 0,
  total_wait_time_seconds INTEGER NOT NULL DEFAULT 0,
  team_size               INTEGER NOT NULL,
  language                TEXT NULL,
  region                  TEXT NULL,
  platform                TEXT NULL,
  created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (guild_id, match_code)
);

CREATE INDEX IF NOT EXISTS idx_five_stack_matches_guild_created
  ON five_stack_matches(guild_id, created_at DESC);

CREATE TABLE IF NOT EXISTS five_stack_match_participants (
  match_id            BIGINT NOT NULL REFERENCES five_stack_matches(id) ON DELETE CASCADE,
  discord_member_id   BIGINT NOT NULL,
  elo_at_match        INTEGER NULL,
  roles_selected      TEXT[] NOT NULL DEFAULT '{}',
  entry_type          INTEGER NOT NULL DEFAULT 1,
  wait_time_seconds   INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (match_id, discord_member_id)
);

CREATE INDEX IF NOT EXISTS idx_five_stack_match_participants_member
  ON five_stack_match_participants(discord_member_id);

CREATE TABLE IF NOT EXISTS five_stack_player_stats (
  guild_id                 BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
  discord_member_id         BIGINT NOT NULL,
  total_matches             INTEGER NOT NULL DEFAULT 0,
  total_wait_time_seconds   INTEGER NOT NULL DEFAULT 0,
  matches_as_solo           INTEGER NOT NULL DEFAULT 0,
  matches_in_group          INTEGER NOT NULL DEFAULT 0,
  last_match_at             TIMESTAMPTZ NULL,
  preferred_role            TEXT NULL,
  PRIMARY KEY (guild_id, discord_member_id)
);

CREATE INDEX IF NOT EXISTS idx_five_stack_player_stats_matches
  ON five_stack_player_stats(guild_id, total_matches DESC);

CREATE TABLE IF NOT EXISTS five_stack_feedback (
  match_id      BIGINT NOT NULL REFERENCES five_stack_matches(id) ON DELETE CASCADE,
  reporter_id   BIGINT NOT NULL,
  rating        INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
  feedback_type TEXT NOT NULL,
  issues        TEXT[] NULL,
  comment       TEXT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (match_id, reporter_id)
);

DO $$
BEGIN
  IF to_regclass('public.teams') IS NOT NULL
     AND to_regclass('public.serveur_id') IS NOT NULL
  THEN
    INSERT INTO guilds (guild_id)
    SELECT DISTINCT s.guild_id
      FROM teams t
      JOIN serveur_id s ON s.id = t.server_id
     WHERE s.guild_id IS NOT NULL
    ON CONFLICT (guild_id) DO NOTHING;

    INSERT INTO five_stack_teams (
      code, guild_id, leader_discord_id, visibility, forum_channel_id,
      thread_id, voice_channel_id, created_at
    )
    SELECT t.code, s.guild_id, t.leader_id, COALESCE(t.visibility, 'public'), t.forum_channel_id,
           t.thread_id, t.voice_channel_id, COALESCE(t.created_at, now())
      FROM teams t
      JOIN serveur_id s ON s.id = t.server_id
     WHERE s.guild_id IS NOT NULL
    ON CONFLICT (guild_id, code) DO NOTHING;
  END IF;

  IF to_regclass('public.team_members') IS NOT NULL
     AND to_regclass('public.serveur_id') IS NOT NULL
  THEN
    INSERT INTO five_stack_team_members (guild_id, team_code, member_discord_id)
    SELECT s.guild_id, tm.team_code, tm.member_id
      FROM team_members tm
      JOIN serveur_id s ON s.id = tm.server_id
      JOIN five_stack_teams fst ON fst.guild_id = s.guild_id AND fst.code = tm.team_code
     WHERE s.guild_id IS NOT NULL
    ON CONFLICT (guild_id, team_code, member_discord_id) DO NOTHING;
  END IF;

  IF to_regclass('public.matchmaking_queue') IS NOT NULL
     AND to_regclass('public.serveur_id') IS NOT NULL
  THEN
    INSERT INTO guilds (guild_id)
    SELECT DISTINCT s.guild_id
      FROM matchmaking_queue q
      JOIN serveur_id s ON s.id = q.server_id
     WHERE s.guild_id IS NOT NULL
    ON CONFLICT (guild_id) DO NOTHING;

    INSERT INTO five_stack_queue (
      guild_id, discord_member_id, entry_type, team_member_ids, language,
      region, platform, desired_team_size, mmr_extended, elo, elo_high,
      elo_low, roles, queued_at
    )
    SELECT s.guild_id, q.discord_member_id,
           CASE WHEN q.entry_type BETWEEN 1 AND 5 THEN q.entry_type ELSE 1 END,
           COALESCE(q.team_member_ids, ARRAY[q.discord_member_id]::BIGINT[]),
           COALESCE(q.langue, 'francais'),
           lower(COALESCE(q.region, 'eu')), lower(COALESCE(q.platform, 'pc')),
           CASE WHEN q.team_size IN (2, 3, 5) THEN q.team_size ELSE 0 END,
           COALESCE(q.mmr_extended, false), q.elo, q.elo_high, q.elo_low,
           COALESCE(q.roles, '{}'::TEXT[]),
           COALESCE(q.timestamp, now())
      FROM matchmaking_queue q
      JOIN serveur_id s ON s.id = q.server_id
     WHERE s.guild_id IS NOT NULL
    ON CONFLICT (guild_id, discord_member_id) DO NOTHING;
  END IF;
END $$;
