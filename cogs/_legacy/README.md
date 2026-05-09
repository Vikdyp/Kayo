# Cogs Legacy

Ce dossier contient les domaines non charges par `bot.py`.

Regles:

- ne pas importer ces modules depuis le noyau actif;
- ne pas ajouter de chemin `cogs._legacy.*` dans `bot.COG_PATHS`;
- ne pas corriger rapidement avec `utils.database`;
- migrer un domaine via repo, service DB, service metier, puis cog avant reactivation.

Domaines actuellement en quarantaine:

- `economy`
- `five_stack`
- `reputation`
- `role_management`
- `scrims`
- `shop`
- `tournaments`
- `troll`
- `twitch`
- `update`

Domaines deja migres vers le noyau actif et retires de cette quarantaine:

- `file_counter`
- `rules`
- `role_management/game_role`
- `role_management/language_role`
- `update/rank_up`
- `voice_chat`
