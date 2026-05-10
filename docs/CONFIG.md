# Configuration runtime

Ce document decrit les variables d'environnement attendues par le bot.
La source de verite cote code est `config.py`.

## Chargement

- `.env` est charge au demarrage par `python-dotenv`.
- `config.load_runtime_settings()` construit un objet `RuntimeSettings`.
- `config.validate_runtime_config()` bloque le demarrage si une variable
  obligatoire manque.
- Les credentials optionnels n'arretent pas le bot, mais generent un warning
  explicite dans les logs.

## Variables obligatoires en production

```env
TEST_MODE=false
DISCORD_TOKEN=...

DATABASE_USER=...
DATABASE_PASSWORD=...
DATABASE_NAME=...
DATABASE_HOST=...
DATABASE_PORT=5432
DATABASE_SSL=false
```

`DATABASE_URL` ou `POSTGRES_DSN` peut remplacer les variables DB separees.

## Variables obligatoires en test

```env
TEST_MODE=true
DISCORD_TOKEN_TEST=...
TEST_GUILD_ID=...

DATABASE_USER=...
DATABASE_PASSWORD=...
DATABASE_TEST_NAME=...
DATABASE_HOST=...
DATABASE_PORT=5432
DATABASE_SSL=false
```

Quand `TEST_MODE=true`, la sync des slash commands se fait uniquement sur
`TEST_GUILD_ID`.

## Integrations optionnelles

```env
HENRIK_VALO_KEY=...
TWITCH_CLIENT_ID=...
TWITCH_CLIENT_SECRET=...
```

- `HENRIK_VALO_KEY` alimente Valorant shop, ranking et suivi MMR.
- Twitch exige les deux variables `TWITCH_CLIENT_ID` et
  `TWITCH_CLIENT_SECRET`. Si une seule est presente, la configuration est
  incomplete.

## Docker Compose

Dans `docker-compose.yml`, le bot force la connexion vers le service PostgreSQL
interne :

```env
DATABASE_HOST=postgres
DATABASE_PORT=5432
DATABASE_SSL=false
```

Il faut donc renseigner surtout `DISCORD_TOKEN`, `DATABASE_PASSWORD`,
`DATABASE_NAME` et les credentials d'integration utiles dans `.env`.

## Changer la configuration

1. Modifier `.env` sur la machine cible.
2. Verifier la configuration Compose :

```bash
docker compose config -q
```

3. Redemarrer le bot :

```bash
docker compose up -d --build bot
```

4. Verifier le runtime :

```bash
docker exec kayo-bot python tools/smoke_runtime.py --skip-migrations
docker logs --since 5m kayo-bot
```
