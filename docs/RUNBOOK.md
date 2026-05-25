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

## Alertes bot

Le timer systemd `kayo-bot-healthcheck.timer` peut surveiller le conteneur
`kayo-bot` toutes les 5 minutes et envoyer une alerte Discord via webhook
lorsque le conteneur passe en erreur, revient OK ou redemarre.

Installation depuis le VPS :

```bash
cd /srv/kayo
install -m 0755 tools/vps/kayo_bot_healthcheck.py /usr/local/sbin/kayo_bot_healthcheck.py
install -m 0644 tools/vps/kayo-bot-healthcheck.service /etc/systemd/system/kayo-bot-healthcheck.service
install -m 0644 tools/vps/kayo-bot-healthcheck.timer /etc/systemd/system/kayo-bot-healthcheck.timer
install -d -m 0700 /etc/kayo
nano /etc/kayo/alerts.env
systemctl daemon-reload
systemctl enable --now kayo-bot-healthcheck.timer
systemctl start kayo-bot-healthcheck.service
```

Contenu attendu dans `/etc/kayo/alerts.env` :

```bash
KAYO_ALERT_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

Commandes de verification :

```bash
systemctl status kayo-bot-healthcheck.timer --no-pager
systemctl status kayo-bot-healthcheck.service --no-pager
journalctl -u kayo-bot-healthcheck.service -n 50 --no-pager
```

## Redemarrage

```bash
cd /srv/kayo
docker compose up -d --build bot
docker compose ps
docker logs --since 2m kayo-bot
```

## Instance Test VPS

Pour tester un changement Discord depuis le VPS sans toucher au conteneur
production `kayo-bot`, utiliser l'instance test separee :

```bash
cd /srv/kayo
tools/vps/run-test-instance.sh status
tools/vps/run-test-instance.sh start --copy-prod-db
tools/vps/run-test-instance.sh logs --since 2m
tools/vps/run-test-instance.sh logs --since 10m --errors
tools/vps/run-test-instance.sh cleanup --drop-test-db
```

Le script cree un worktree temporaire `/tmp/kayo-test-*`, une image
`kayo-bot-test:<run_id>` et un conteneur `kayo-bot-test` connecte au reseau de
`kayo-postgres`. Il force `TEST_MODE=true`, `DATABASE_HOST=postgres` et utilise
`DATABASE_TEST_NAME`; la sync Discord doit donc rester limitee a
`TEST_GUILD_ID`.

Garde-fous :

- `start` refuse un checkout `/srv/kayo` avec fichiers tracked modifies.
- `start --copy-prod-db` recree `DATABASE_TEST_NAME` depuis `DATABASE_NAME` et
  refuse si les deux noms sont identiques.
- `cleanup --drop-test-db` supprime seulement les ressources test connues :
  `kayo-bot-test`, `kayo-bot-test:*`, `/tmp/kayo-test-*`, les patchs test
  `/tmp/kayo-test-*.patch` et la DB `DATABASE_TEST_NAME`.
- Ne pas utiliser `docker system prune` pour ce workflow.

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
