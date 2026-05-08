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
