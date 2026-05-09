# Cogs Legacy

Ce dossier contient les domaines non charges par `bot.py`.

Regles:

- ne pas importer ces modules depuis le noyau actif;
- ne pas ajouter de chemin `cogs._legacy.*` dans `bot.COG_PATHS`;
- ne pas corriger rapidement avec `utils.database`;
- migrer un domaine via repo, service DB, service metier, puis cog avant reactivation.

Domaines encore en quarantaine:

- `economy`
- `five_stack`
- `role_management/auto_role`
- `role_management/role_combination`
- `scrims`
- `shop`
- `tournaments`
- `troll`
- `update`

Domaines deja migres vers le noyau actif. Les anciennes copies peuvent rester
ici temporairement comme archive de comparaison jusqu'au nettoyage final:

- `file_counter`
- `reputation`
- `rules`
- `role_management/game_role`
- `role_management/language_role`
- `twitch`
- `update/permissions_report`
- `update/rank_up`
- `voice_chat`
