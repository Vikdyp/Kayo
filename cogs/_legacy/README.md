# Cogs Legacy

Ce dossier contient les domaines non charges par `bot.py`.

Regles:

- ne pas importer ces modules depuis le noyau actif;
- ne pas ajouter de chemin `cogs._legacy.*` dans `bot.COG_PATHS`;
- ne pas corriger rapidement avec `utils.database`;
- migrer un domaine via repo, service DB, service metier, puis cog avant reactivation.

Domaines encore en quarantaine:

- `five_stack`
- `scrims`
- `shop`

Domaines supprimes du legacy car remplaces dans le noyau actif:

- `role_management/auto_role`: ancien listener vide; la reaplication du ban
  interne au retour membre est geree par `cogs.moderation.moderation`.
- `role_management/role_combination`: fonctionnalite desactivee, non utilisee.
- `troll`: ancienne version DB supprimee; la reponse `quoi`/`feur` vit dans
  `cogs.fun.quoi_feur`.
- `update/test`: ancien rapport de permissions remplace par `cogs.admin.permissions_report`.
- `update/online_count_updater`: migre vers `cogs.ranking.online_count`.
- `economy`: migre vers `cogs.economy.economy`.
- `tournaments`: migre vers `cogs.tournaments.tournament`.

Domaines deja migres vers le noyau actif:

- `file_counter`
- `economy`
- `reputation`
- `rules`
- `role_management/game_role`
- `role_management/language_role`
- `tournaments`
- `twitch`
- `update/permissions_report`
- `update/online_count_updater`
- `update/rank_up`
- `voice_chat`
