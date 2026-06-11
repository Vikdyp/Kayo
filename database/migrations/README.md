# Database Migrations

Migrations are forward-only and must preserve existing data. New migrations must
avoid destructive SQL unless a previous migration already created an explicit
backup table and the data loss risk has been reviewed.

Render production has one historical entry in `schema_migrations` that is not in
this repository anymore:

- `010_refactor_valorant_ranking_tables.sql`

That version was applied before the current defensive Valorant migrations were
committed. Do not recreate it, do not delete it from Render, and do not edit
`schema_migrations` by hand. The read-only schema audit accepts that exact
historical version and treats any other unknown migration as drift.

## Identity v2

`022_identity_v2.sql` creates `discord_users_v2` and `guild_members_v2` without
dropping or renaming the existing identity tables. It backfills from `users` and
`guild_members` so the runtime can keep using the current schema while domains
are migrated one by one.

`023_domain_v2_schema.sql` creates the remaining v2 domain tables without
backfilling data. Backfill migrations must stay domain-scoped and non
destructive.

`024_simple_v2_backfill.sql` backfills low-risk tables: configuration,
automod settings, daily stats, file counters, Twitch streamers, Valorant shop
notifications, economy, reputation, user profiles, and message deletion history.

Complex domain backfills are split by responsibility:

- `025_valorant_v2_backfill.sql` backfills linked Valorant accounts, current
  rank state, and rank snapshots.
- `026_moderation_v2_backfill.sql` backfills moderation cases, sanctions, role
  snapshots, and unban requests.
- `027_scrims_tournaments_v2_backfill.sql` backfills scrims, scrim
  participants, tournaments, teams, and tournament players.
- `028_five_stack_v2_backfill.sql` backfills teams, queue entries, queue roles,
  matches, participants, participant roles, feedback, and player stats.

`029_mmr_history_metadata.sql` enriches the active Valorant MMR history with
account-scoped metadata (`puuid`, RR delta, match id, source) and backfill
status fields on `valorant_info`. It is additive and keeps the runtime on the
current Valorant tables.

After these migrations are committed, a live schema audit will report drift until
the pending v2 migrations have been applied to the target database. Run a
`pg_dump` backup before applying them on production.
