# Déploiement Docker sur VPS

Ce projet peut tourner avec Docker Compose : un conteneur `bot` et un conteneur
PostgreSQL privé au réseau Docker.

## Préparer le VPS

Docker est requis côté serveur. Sur le VPS actuel, Docker et Docker Compose sont
déjà installés.

Créer un dossier applicatif :

```bash
mkdir -p /srv/kayo
cd /srv/kayo
```

Copier le dépôt dans `/srv/kayo` avec `git clone`, `rsync`, `scp` ou une CI.

En local/CI, utiliser `requirements-dev.txt` pour installer les outils de test.
L'image Docker installe uniquement `requirements.txt`.

## Fichier d'environnement

Créer le fichier `.env` depuis le modèle :

```bash
cp .env.docker.example .env
nano .env
```

Variables minimales :

- `DISCORD_TOKEN`
- `DATABASE_PASSWORD`
- `HENRIK_VALO_KEY`

Variables optionnelles :

- `TWITCH_CLIENT_ID`
- `TWITCH_CLIENT_SECRET`
- `DISCORD_TOKEN_TEST`
- `TEST_GUILD_ID`

Dans Docker Compose, le bot utilise toujours le service PostgreSQL interne :

- `DATABASE_HOST=postgres`
- `DATABASE_PORT=5432`
- `DATABASE_SSL=false`

Ces valeurs sont forcées par `docker-compose.yml` pour éviter d'utiliser par
erreur une base externe depuis le conteneur.

## Build et lancement

```bash
docker compose build
docker compose up -d
docker compose logs -f bot
```

Le bot applique les migrations au démarrage via `bot.py`.

## Vérifications utiles

```bash
docker compose ps
docker compose logs --tail=200 bot
docker compose exec bot python -m database.schema_contract --json
docker compose exec bot python tools/smoke_runtime.py --skip-migrations
```

## Sauvegarde PostgreSQL

Avant toute migration majeure :

```bash
mkdir -p /srv/kayo/backups
docker compose exec -T postgres pg_dump -U "$DATABASE_USER" "$DATABASE_NAME" \
  > "/srv/kayo/backups/kayo_$(date +%Y%m%d_%H%M%S).sql"
```

Restauration dans une base vide :

```bash
docker compose exec -T postgres psql -U "$DATABASE_USER" "$DATABASE_NAME" \
  < /srv/kayo/backups/backup.sql
```

## Migration DB v2

Les migrations v2 `022_identity_v2.sql` à `028_five_stack_v2_backfill.sql`
sont non destructives, mais elles doivent quand même être précédées d'un backup.

- `022_identity_v2.sql` ajoute les tables d'identité v2 et backfill depuis les
  tables actuelles.
- `023_domain_v2_schema.sql` crée toutes les tables domaine v2 sans backfill.
- `024_simple_v2_backfill.sql` backfill les domaines simples.
- `025_valorant_v2_backfill.sql` backfill Valorant.
- `026_moderation_v2_backfill.sql` backfill la modération et les demandes de
  déban.
- `027_scrims_tournaments_v2_backfill.sql` backfill scrims et tournois.
- `028_five_stack_v2_backfill.sql` backfill five-stack.

Séquence recommandée :

```bash
docker compose exec -T postgres pg_dump -U "$DATABASE_USER" "$DATABASE_NAME" \
  > "/srv/kayo/backups/before_identity_v2_$(date +%Y%m%d_%H%M%S).sql"

docker compose run --rm bot python -m database.migrate
docker compose run --rm bot python -m database.schema_contract --json
```

Ne pas supprimer les anciennes tables `users` et `guild_members` à ce stade :
le bot continue volontairement à les utiliser pendant la migration progressive
des domaines.

## Mise à jour

```bash
git pull
docker compose build bot
docker compose up -d
docker compose logs -f bot
```

## Arrêt

```bash
docker compose down
```

Ne pas utiliser `docker compose down -v` sauf si l'objectif est de supprimer les
données PostgreSQL et les logs persistants.
