# Audit Kayo et VPS - 2026-05-10

## Perimetre

- Bot Discord Kayo dans `D:\Programmation\Python\Discord\Kayo`.
- VPS Kayo, utilisateur `root`, acces par cle SSH dediee uniquement.
- Projet serveur touche: `/srv/kayo`.
- Projets explicitement preserves: `/srv/bodylab`, `/srv/cypher-trading-bot`, `/root/trading-bot`, `/root/trading-bot-staging`.

## Etat final

- Tests locaux: `195 passed, 1 warning`.
- Audit dependances: aucune vulnerabilite connue via `pip-audit`.
- Audit statique: `0 High`, `10 Medium`, `7 Low` via Bandit.
- VPS: SSH par cle toujours fonctionnel apres changements.
- Kayo: `kayo-bot` redemarre et connecte comme `kayo#9928`.
- Autres conteneurs: toujours `Up` apres deploy.
- Sauvegardes serveur creees avant remplacements: `/root/kayo-backups/20260510012456`, `/root/kayo-backups/behavior-fixes-20260510153651`.

## Correctifs appliques

- `bot.py`: remplacement de `discord.Intents.all()` par des intents explicites.
- `cogs/accueil/stalker.py`: `!embed_statistique` limite aux administrateurs.
- `cogs/scrims/scrims.py`: `!init_scrim` limite aux administrateurs.
- `cogs/moderation/views/spam_confirmation_view.py`: re-verification des permissions `ban_members` ou `administrator` sur les boutons spam.
- `cogs/moderation/services/internal_ban_workflow.py`: sauvegarde et restauration des roles par serveur lors des bans/debans internes.
- `tests/test_moderation_internal_ban_workflow.py`: ajout de tests multi-serveurs.
- VPS `/srv/kayo`: permissions corrigees en `755` pour les dossiers, `644` pour les fichiers, `.env` conserve en `600`.
- VPS: installation et activation de fail2ban avec jail `sshd`.

## Inventaire des commandes Discord

### Slash et groupes

29 handlers slash/group ont ete detectes dans le code, avec 16 commandes globales synchronisees au demarrage.

- `permissions_report`
- `setstatus`
- `salon`
- `roles`
- `economy daily`
- `economy shop`
- `economy inventaire`
- `economy trade`
- `team create`
- `team join`
- `team leave`
- `team kick`
- `team delete`
- `team list`
- `team info`
- `matchmaking stats`
- `matchmaking history`
- `matchmaking server`
- `matchmaking leaderboard`
- `matchmaking feedback`
- `automod`
- `clean`
- `moderation`
- `mmr_track`
- `reputation`
- `profile_set`
- `profile_show`
- `tournoi`
- `streamer`

### Prefix `!`

- `!embed_statistique`
- `!init_counter`
- `!start_queue`
- `!role_counters`
- `!send_deban`
- `!send_embed_rang`
- `!ping`
- `!setup_roles`
- `!setup_language`
- `!setup_rules`
- `!init_scrim`

### Listeners

- Accueil et statistiques membres: `on_member_join`, `on_member_remove`.
- Status: `on_ready`.
- Five-stack: `on_ready`, `on_member_remove`.
- Fun: `on_message`.
- Automod: `on_message`.
- Moderation: `on_member_join`, `on_member_update`.
- Ranking: `on_ready`, `on_member_join`, `on_member_remove`, `on_presence_update`, `on_member_update`.
- Scrims et tournois: `on_ready`.
- Vocaux temporaires: `on_voice_state_update`.

### Taches planifiees

- `daily_update`
- `process_queue_task_loop`
- `stale_task`
- `cleanup_teams_task`
- `voice_cleaner_task`
- `check_bans_expired`
- `update_roles_loop`
- `refresh_roles_cache_task`
- `check_loop`
- `refresh_rank_counts`
- `scrim_end_checker`
- `check_shop_task`
- `check_streams_task`
- `voice_check_loop`

## Comportement observe au demarrage

Les logs du conteneur montrent:

- connexion avec token statique Discord;
- ouverture du pool Postgres;
- application des migrations;
- initialisation des services: accueil, clean, automod, moderation, economie, five-stack, file counter, reputation, rules, scrims, Valorant shop, tournaments, Twitch, temp voice, ranking/MMR;
- chargement des cogs actifs;
- synchronisation globale de 16 commandes;
- connexion Gateway Discord;
- rechargement des vues persistantes de deban et ranking;
- connexion finale comme `kayo#9928`;
- rafraichissement du cache de roles et des compteurs de presence.

## Commandes executees et verifications

### Local

- `Select-String` et `Get-Content` pour inspecter les fichiers cibles.
- `.venv\Scripts\python.exe -m pytest tests\test_moderation_internal_ban_workflow.py`
- `.venv\Scripts\python.exe -m pytest`
- `git diff -- ...`
- `git status --short`
- `uvx bandit -r bot.py cogs core database integrations tools -f txt -q`
- `uvx pip-audit -r requirements.txt`
- script Python AST local pour inventorier les commandes, listeners et taches.
- `Get-FileHash -Algorithm SHA256 ...`

### SSH et sauvegarde

- Test SSH initial: une premiere commande a echoue a cause de guillemets distants mal echappes.
- Test SSH valide ensuite avec la cle dediee: `ssh -i <cle-dediee> root@<vps> hostname`
- Sauvegarde des fichiers modifies vers `/root/kayo-backups/20260510012456`.
- Copie par `scp` des six fichiers modifies vers `/srv/kayo`.
- Verification SHA-256 locale et distante: hashes identiques.

### VPS securite

- `apt-get update`
- `DEBIAN_FRONTEND=noninteractive apt-get install -y fail2ban`
- creation de `/etc/fail2ban/jail.d/sshd.local`
- `systemctl enable --now fail2ban`
- `systemctl restart fail2ban`
- `fail2ban-client -t`
- `fail2ban-client status sshd`
- test SSH final par cle: OK.

### VPS Kayo

- `docker compose config -q` depuis `/srv/kayo`.
- `docker compose up -d --build bot` depuis `/srv/kayo`.
- `docker ps --filter name=kayo`.
- `docker ps` pour verifier que les autres projets restent actifs.
- `docker logs --tail=120 kayo-bot`.
- `docker logs --since=90s kayo-bot`.

## Points restant a surveiller

- Bandit signale encore 10 alertes Medium sur SQL dynamique. Les usages vus reposent sur listes blanches ou constantes internes, mais ils meritent une annotation ou une refactorisation future pour reduire le bruit.
- Bandit signale 7 Low: `random` non cryptographique pour des usages non sensibles et deux `try/except/pass`.
- `/root/trading-bot/.env` etait lisible en `644`, mais il est hors perimetre Kayo et n'a pas ete modifie.
