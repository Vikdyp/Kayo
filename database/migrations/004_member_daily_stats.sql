-- 004_member_daily_stats.sql
-- Stats quotidiennes join/leave par guild (date en UTC)

CREATE TABLE IF NOT EXISTS member_daily_stats (
    guild_id    BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
    date        DATE NOT NULL,
    join_count  INTEGER NOT NULL DEFAULT 0 CHECK (join_count >= 0),
    leave_count INTEGER NOT NULL DEFAULT 0 CHECK (leave_count >= 0),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, date)
);

CREATE INDEX IF NOT EXISTS idx_member_daily_stats_date
    ON member_daily_stats(guild_id, date DESC);
