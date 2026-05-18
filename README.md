# Kayo

Kayo est un bot Discord Python base sur `discord.py`.

Les consignes locales pour Codex et agents de code vivent dans
[`AGENTS.md`](AGENTS.md).

Le refactor en cours garde uniquement le noyau actif charge par `bot.py`:

- configuration des salons et roles
- reglement et selection de roles
- accueil et statistiques membres
- moderation, automod et demandes d'unban
- compteur de fichiers et salons vocaux temporaires
- notifications Twitch partenaires
- ranking Valorant, notifications de rang et suivi MMR

Les anciens domaines sont places dans `cogs/_legacy/`. Ils restent hors chargement
tant qu'ils ne respectent pas la nouvelle architecture.

## Architecture Cible

La documentation detaillee vit dans [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

- `cogs/`: commandes, permissions, embeds, vues et interactions Discord.
- `cogs/*/services/`: logique metier, validation, orchestration fonctionnelle.
- `cogs/_legacy/`: anciens domaines non charges par le bot.
- `database/services/`: transactions, mapping Discord ID vers IDs internes,
  orchestration multi-repos.
- `database/repos/`: SQL pur et mapping row vers dataclass.
- `integrations/`: appels HTTP, modeles Pydantic et erreurs API.
- `core/`: assemblage runtime et injection des services.
- `database/migrations/`: migrations forward-only.
- `tools/`: scripts manuels hors runtime et hors CI metier.
- `docs/`: documentation projet et archives non runtime.

Regle importante: un service metier ne doit pas importer `database.repos` ni
`asyncpg`.

## Prerequis

- Python 3.12
- PostgreSQL accessible par `asyncpg`
- Token Discord
- Cle Henrik Valorant pour le ranking/MMR
- Identifiants Twitch Helix pour les notifications de live, optionnels

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

Copier `.env.example` vers `.env`, puis renseigner les valeurs.

## Variables D'Environnement

Variables principales:

- `DISCORD_TOKEN`: token du bot en production.
- `DISCORD_TOKEN_TEST`: token utilise quand `TEST_MODE=true`.
- `TEST_MODE`: `true` pour utiliser la base et le token de test.
- `TEST_GUILD_ID`: guild Discord utilisee pour la sync slash en test.
- `DATABASE_USER`
- `DATABASE_PASSWORD`
- `DATABASE_NAME`
- `DATABASE_TEST_NAME`
- `DATABASE_HOST`
- `DATABASE_PORT`
- `DATABASE_SSL`
- `HENRIK_VALO_KEY`: cle API Henrik Valorant.
- `TWITCH_CLIENT_ID`: client ID Twitch Helix, optionnel.
- `TWITCH_CLIENT_SECRET`: secret Twitch Helix, optionnel.

## Checks

```bash
python -m compileall -q bot.py core cogs database integrations tests tools
python -m pytest -q
python tools/smoke_runtime.py
```

Les tests ne doivent pas appeler l'API Henrik reelle. Le smoke runtime ouvre la
DB configuree par `.env`, applique les migrations, construit le conteneur de
services, charge les cogs actifs sans gateway Discord, puis ferme DB/HTTP.

## Lancement

```bash
python bot.py
```

Au demarrage, le bot ouvre le pool DB, applique les migrations, initialise les
services, charge les cogs actifs, puis synchronise les commandes slash.

## Docker / VPS

Le projet fournit un `Dockerfile`, un `docker-compose.yml` avec PostgreSQL 18 et
un modèle `.env.docker.example`.

Documentation:

- [`docs/CONFIG.md`](docs/CONFIG.md)
- [`docs/RUNBOOK.md`](docs/RUNBOOK.md)
- [`docs/DEPLOY_DOCKER.md`](docs/DEPLOY_DOCKER.md)
- [`docs/OPERATIONS_LOG.md`](docs/OPERATIONS_LOG.md)
- [`docs/DATABASE_V2_PROPOSAL.md`](docs/DATABASE_V2_PROPOSAL.md)
