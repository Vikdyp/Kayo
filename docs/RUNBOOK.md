# Runbook exploitation

Ce runbook sert aux operations courantes sur Kayo. Il ne doit pas contenir de
secret. Les tokens, mots de passe et chemins de cle SSH restent dans le coffre
ou les notes d'exploitation privees.

## Etat rapide

Depuis le VPS :

```bash
cd /srv/kayo
docker compose ps
docker logs --tail 200 kayo-bot
systemctl list-timers --all | grep kayo-postgres-backup
```

Verification runtime sans connexion gateway Discord :

```bash
docker exec kayo-bot python tools/smoke_runtime.py --skip-migrations
```

## Logs utiles

```bash
docker logs -f kayo-bot
docker logs --since 10m kayo-bot
docker logs --since 10m kayo-bot 2>&1 | grep -Ei 'error|exception|traceback|failed|critical'
```

## Redemarrage

```bash
cd /srv/kayo
docker compose up -d --build bot
docker compose ps
docker logs --since 2m kayo-bot
```

## Backup PostgreSQL

Le timer systemd `kayo-postgres-backup.timer` lance un dump quotidien.

Commandes :

```bash
systemctl status kayo-postgres-backup.timer --no-pager
systemctl start kayo-postgres-backup.service
find /srv/kayo/backups/postgres -maxdepth 1 -type f -printf '%TY-%Tm-%Td %TH:%TM %s %p\n' | sort | tail
```

Les dumps sont au format custom `pg_dump -Fc`. Garder aussi une copie hors VPS.

## Restaurer un dump

Restaurer seulement pendant une fenetre de maintenance. Faire un backup juste
avant, arreter le bot, puis restaurer dans la base cible.

```bash
cd /srv/kayo
systemctl start kayo-postgres-backup.service
docker compose stop bot
cat /srv/kayo/backups/postgres/kayo-postgres-YYYYMMDDTHHMMSSZ.dump \
  | docker compose exec -T postgres pg_restore --clean --if-exists -U "$DATABASE_USER" -d "$DATABASE_NAME"
docker compose up -d bot
docker exec kayo-bot python tools/smoke_runtime.py --skip-migrations
```

## Procedure de release

Avant de deployer :

```bash
python -m compileall -q bot.py core cogs database integrations tests tools
python -m pytest -q
uvx pip-audit -r requirements.txt
uvx bandit -r bot.py cogs core database integrations tools
```

Sur le VPS :

```bash
cd /srv/kayo
tools/vps/deploy-from-git.sh
```

Le script verifie que le checkout Git est propre, fait un `git pull --ff-only`,
lance un backup PostgreSQL, rebuild le bot, execute le smoke runtime et affiche
les erreurs critiques recentes.

## Rollback

Si `/srv/kayo` est un checkout Git, revenir au commit precedent puis rebuild :

```bash
cd /srv/kayo
git checkout <previous-commit>
docker compose up -d --build bot
```

Sur le VPS actuel, lorsqu'un deploiement manuel remplace des fichiers, creer
avant remplacement une sauvegarde sous `/root/kayo-backups/`. Pour rollback :

```bash
cp -a /root/kayo-backups/<backup-id>/. /srv/kayo/
cd /srv/kayo
docker compose up -d --build bot
```

## Incident

1. Lire les logs recents du bot.
2. Verifier `docker compose ps`.
3. Lancer le smoke runtime.
4. Si la DB est suspecte, lancer un backup avant toute action.
5. Revenir au dernier deploy connu stable si l'incident suit une release.
6. Noter l'action dans `docs/OPERATIONS_LOG.md`.

## Permissions Discord

Le bot ne devrait pas garder `administrator` a long terme. Avant de retirer
cette permission :

1. Lister les commandes et workflows actifs.
2. Verifier les permissions minimales par domaine.
3. Tester sur une guild de test avec `TEST_MODE=true`.
4. Reduire les permissions en production pendant une fenetre surveillee.
