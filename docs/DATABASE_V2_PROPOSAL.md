# Proposition de schéma DB v2

Objectif : nettoyer le modèle sans casser le bot en production. La migration
doit être progressive et réversible au moins jusqu'au basculement final.

## Constats sur le schéma actuel

- Identité utilisateur mixte : certaines tables référencent `users.user_id`,
  d'autres stockent directement des `discord_id`.
- Configuration Discord très flexible (`guild_channels`, `guild_roles`), mais
  sans catalogue typé des clés attendues par feature.
- Certaines tables métier stockent des listes en colonnes tableau ou JSON
  (`roles`, `team_member_ids`, `player_discord_ids`), ce qui complique les
  contraintes, les requêtes et les exports.
- Plusieurs migrations contiennent encore de la logique de compatibilité legacy.
- Les domaines critiques n'ont pas tous la même convention de timestamps,
  statuts, contraintes et relations.

## Principes cibles

- Une seule identité canonique :
  - `discord_users` pour l'utilisateur global Discord.
  - `guild_members` pour son état dans un serveur.
  - Toutes les tables métier référencent l'une de ces deux tables.
- Les IDs Discord restent des `BIGINT`, mais ne remplacent plus les relations
  internes quand une relation DB est nécessaire.
- Les listes métier importantes deviennent des tables d'association.
- Les configurations par clé restent possibles, mais avec un catalogue par
  feature pour pouvoir auditer les clés manquantes.
- Les migrations v2 sont non destructives au début : création de nouvelles
  tables, backfill, lecture double si nécessaire, puis bascule.

## Schéma cible haut niveau

### Core

- `guilds(guild_id, name_cache, created_at, updated_at)`
- `discord_users(id, discord_id, created_at, last_seen_at)`
- `guild_members(id, guild_id, discord_user_id, is_member, joined_at, left_at, updated_at)`
- `feature_keys(feature, key, value_type, required, description)`
- `guild_channel_configs(guild_id, key, channel_id, created_at, updated_at)`
- `guild_role_configs(guild_id, key, role_id, name_cache, created_at, updated_at)`
- `persistent_messages(guild_id, message_type, channel_id, message_id, created_at, updated_at)`

### Modération

- `moderation_cases(id, guild_id, target_member_id, moderator_member_id, case_type, reason, created_at)`
- `moderation_sanctions(id, case_id, sanction_type, status, starts_at, ends_at, resolved_at)`
- `moderation_role_snapshots(guild_id, member_id, role_id, created_at)`
- `unban_requests(id, guild_id, requester_user_id, channel_id, message_id, reason, status, created_at, resolved_at, resolved_by_member_id)`

### Automod

- `automod_settings(guild_id, scam_detection_enabled, spam_detection_enabled, spam_channel_threshold, spam_time_window, delete_messages_on_scam, delete_period_hours, created_at, updated_at)`
- `automod_allowed_roles(guild_id, role_id)`
- `automod_allowed_channels(guild_id, channel_id)`
- `automod_scam_patterns(guild_id, pattern)`
- `automod_scam_domains(guild_id, domain)`

### Valorant

- `valorant_accounts(id, discord_user_id, puuid, name, tag, region, platform, account_level, card_uuid, title_uuid, created_at, updated_at)`
- `valorant_rank_state(account_id, rank_name, elo, season, act, tracking_enabled, is_active, error_count, last_error_at, last_checked_at, last_notification)`
- `valorant_rank_snapshots(id, account_id, season, act, recorded_at, elo, is_win)`
- `valorant_sent_bundles(guild_id, bundle_uuid, notified_at)`

### Five-stack

- `five_stack_teams(id, guild_id, code, leader_member_id, visibility, status, forum_channel_id, thread_id, voice_channel_id, created_at, updated_at)`
- `five_stack_team_members(team_id, member_id, joined_at)`
- `five_stack_queue(id, guild_id, member_id, entry_type, team_id, language, region, platform, desired_team_size, mmr_extended, elo, elo_low, elo_high, queued_at)`
- `five_stack_queue_roles(queue_id, role_key)`
- `five_stack_matches(id, guild_id, match_code, voice_channel_id, quality_score, elo_spread, avg_elo, team_size, language, region, platform, created_at)`
- `five_stack_match_participants(match_id, member_id, elo_at_match, entry_type, wait_time_seconds)`
- `five_stack_match_roles(match_id, member_id, role_key)`
- `five_stack_feedback(match_id, reporter_member_id, rating, feedback_type, issues, comment, created_at)`
- `five_stack_player_stats(guild_id, member_id, total_matches, total_wait_time_seconds, matches_as_solo, matches_in_group, last_match_at, preferred_role)`

### Autres domaines

- `member_daily_stats(guild_id, date, join_count, leave_count, created_at, updated_at)`
- `message_deletions(id, guild_id, deleted_by_member_id, source, channel_id, channel_name, deletion_type, target_user_id, target_user_tag, message_count, created_at)`
- `economy_profiles(guild_id, member_id, balance, last_daily_claim, created_at, updated_at)`
- `economy_inventory_items(guild_id, member_id, item_name, quantity, created_at, updated_at)`
- `file_counters(guild_id, channel_id, message_id, added_count, completed_count, created_at, updated_at)`
- `reputation_events(id, guild_id, reporter_member_id, target_member_id, event_type, event_date, count, reason, created_at, updated_at)`
- `user_profiles(discord_user_id, genre, valorant_tracker, lft, note, created_at, updated_at)`
- `twitch_streamers(guild_id, streamer_login, created_at, updated_at)`
- `scrims(id, guild_id, creator_member_id, scheduled_at, map_name, rank_name, notes, channel_id, message_id, status, created_at, updated_at, ended_at)`
- `scrim_participants(scrim_id, team_index, member_id)`
- `tournaments(id, guild_id, tournament_name, max_teams, registration_start, registration_end, tournament_date, status, registration_channel_id, registration_message_id, created_at, updated_at, closed_at)`
- `tournament_teams(id, tournament_id, captain_member_id, team_name, coach_member_id, created_at, updated_at)`
- `tournament_team_players(team_id, member_id, slot_type)`

## Plan de migration recommandé

1. **Préparation**
   - Sauvegarde `pg_dump`.
   - Audit `python -m database.schema_contract --json`.
   - Gel des changements DB non liés à la migration.

2. **Création v2 non destructive**
   - Ajouter les tables v2 avec suffixe temporaire ou noms finaux encore non
     utilisés.
   - Ajouter les index et contraintes.
   - Aucun drop.

3. **Backfill**
   - Remplir `discord_users` et `guild_members`.
   - Backfill domaine par domaine.
   - Ajouter des tests de comparaison entre anciennes et nouvelles lectures.

4. **Adaptation code**
   - Migrer un domaine à la fois : repo v2, service DB, tests.
   - Garder les interfaces des services métier stables autant que possible.

5. **Bascule**
   - Déployer en maintenance courte.
   - Rejouer le backfill final.
   - Activer les repos v2.
   - Garder les anciennes tables en lecture seule pendant une période de sûreté.

6. **Nettoyage**
   - Supprimer les anciennes tables seulement après validation production.
   - Supprimer la compatibilité legacy des migrations historiques dans une
     nouvelle ligne de base si on accepte de repartir d'un dump v2.

## Première tranche concrète

La première tranche implémentée côté dépôt commence par l'identité :

- migration `022_identity_v2.sql`
- création de `discord_users_v2`
- création de `guild_members_v2`
- backfill depuis `users` et `guild_members`

La deuxième tranche implémentée pose le schéma cible complet :

- migration `023_domain_v2_schema.sql`
- création des tables v2 pour configuration, modération, automod, Valorant,
  five-stack, économie, réputation, scrims, tournois, Twitch, compteurs et stats
- aucun backfill domaine dans cette migration
- aucune table existante supprimée ou renommée

La troisième tranche implémentée backfill les domaines simples :

- migration `024_simple_v2_backfill.sql`
- configuration salons/roles/messages persistants
- automod settings et listes normalisées
- stats quotidiennes, compteurs de fichiers, Twitch, Valorant shop
- économie, réputation, profils utilisateurs, historique de suppressions
- aucune suppression ou modification destructive des tables actuelles

La quatrième tranche implémentée backfill les domaines complexes :

- migration `025_valorant_v2_backfill.sql` pour comptes Valorant, état de rang
  courant et historique MMR
- migration `026_moderation_v2_backfill.sql` pour cas de modération, sanctions,
  snapshots de rôles et demandes de déban
- migration `027_scrims_tournaments_v2_backfill.sql` pour scrims, participants,
  tournois, équipes et joueurs
- migration `028_five_stack_v2_backfill.sql` pour five-stack : teams, queue,
  matchs, participants, rôles, feedback et stats
- ces migrations restent additives et ne suppriment pas les anciennes tables

Étapes suivantes :

- ajouter les repos/services v2
- migrer un domaine faible risque, par exemple `economy`
- ajouter des tests de comparaison old/v2 sur un dump restauré

Cette tranche valide le modèle et la conservation de données côté migration,
mais le runtime continue d'utiliser les anciennes tables tant que les
repos/services v2 n'ont pas été activés domaine par domaine.
