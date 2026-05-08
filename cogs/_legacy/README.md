# Cogs Legacy

Ce dossier contient les domaines non charges par `bot.py`.

Regles:

- ne pas importer ces modules depuis le noyau actif;
- ne pas ajouter de chemin `cogs._legacy.*` dans `bot.COG_PATHS`;
- ne pas corriger rapidement avec `utils.database`;
- migrer un domaine via repo, service DB, service metier, puis cog avant reactivation.

Domaines actuellement en quarantaine:

- `economy`
- `file_counter`
- `five_stack`
- `reputation`
- `role_management`
- `rules`
- `scrims`
- `shop`
- `tournaments`
- `troll`
- `twitch`
- `update`
- `voice_chat`
