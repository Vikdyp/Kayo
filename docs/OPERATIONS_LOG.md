# Journal operations

Ce journal garde les decisions et actions techniques importantes. Il complete
les commits et aide la personne suivante a comprendre l'etat reel du projet.

## 2026-05-10 - Audit complet local + VPS

- Tests locaux initialement OK.
- `pip-audit` sans vulnerabilite connue.
- Bandit signalait surtout du SQL dynamique et quelques usages faibles de
  generateurs pseudo-aleatoires.
- VPS sain : Docker actif, `kayo-bot` up, `kayo-postgres` healthy, SSH sans mot
  de passe, `.env` protege.
- Discord live : un serveur, 16 commandes globales, objets persistants DB
  coherents.
- Point faible majeur identifie : pas de backup automatise et deploiement VPS
  hors Git.

## 2026-05-10 - Corrections securite et runtime

- Echec explicite si une extension se charge sans enregistrer de cog.
- Helper d'erreur Discord pour choisir `response` ou `followup`.
- Smoke runtime corrige pour transmettre les credentials Twitch.
- SQL dynamique retire des repos critiques ou remplace par des requetes
  statiques.
- Codes FiveStack generes avec `secrets`.
- Timer systemd PostgreSQL installe et teste sur le VPS.
- Bot reconstruit et redemarre en production.
- Verification production OK : 27 cogs charges par le smoke test, logs recents
  sans erreur critique.

## 2026-05-10 - Configuration et documentation exploitation

- `config.py` centralise maintenant la configuration dans `RuntimeSettings`.
- Validation de demarrage explicite pour token Discord, DB et mode test.
- Warnings operationnels pour Henrik/Twitch quand les credentials optionnels
  limitent des features.
- Ajout de `docs/CONFIG.md` et `docs/RUNBOOK.md`.

## 2026-05-10 - Deploiement Git active sur le VPS

- Les changements valides ont ete commits et pousses sur `origin/master`.
- `/srv/kayo` est maintenant un checkout Git propre.
- L'ancien dossier manuel est conserve dans
  `/srv/kayo.manual-20260510T201135Z`.
- `.env` a ete preserve avec permissions `600`.
- Les backups PostgreSQL ont ete preserves dans `/srv/kayo/backups/postgres`.
- `tools/vps/deploy-from-git.sh` est executable et a ete teste en production :
  pull fast-forward, backup, rebuild Docker, restart bot et smoke runtime.
- Etat verifie apres bascule : `kayo-bot` up, `kayo-postgres` healthy, logs
  recents sans erreur critique.

## 2026-05-18 - Alerte healthcheck bot sur VPS

- Ajout d'un healthcheck systemd optionnel pour `kayo-bot`.
- Commit pousse sur `origin/master`, puis pull fast-forward sur `/srv/kayo`.
- Installation VPS :
  - `/usr/local/sbin/kayo_bot_healthcheck.py`
  - `/etc/systemd/system/kayo-bot-healthcheck.service`
  - `/etc/systemd/system/kayo-bot-healthcheck.timer`
  - secret webhook hors Git dans `/etc/kayo/alerts.env`
- Le timer `kayo-bot-healthcheck.timer` tourne toutes les 5 minutes.
- Perimetre verifie : le script cible uniquement `docker inspect kayo-bot` et
  ecrit son etat dans `/var/lib/kayo/bot-healthcheck-state.json`.
- Aucun rebuild ni redemarrage du bot.
- Autres conteneurs verifies actifs apres installation : `bodylab-app`,
  `bodylab-postgres`, `cypher-trading-bot-dashboard-1`,
  `cypher-trading-bot-live-bot-1`, `cypher-trading-bot-paper-bot-1`.
- Premier passage OK : `Kayo bot OK`, sans alerte envoyee car l'etat initial
  etait sain.

## Suite recommandee

1. Copier automatiquement les backups PostgreSQL hors VPS.
2. Reduire progressivement les permissions Discord du bot.
3. Tester une restauration backup Hostinger ou documenter sa procedure exacte.
