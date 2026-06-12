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

## 2026-05-24 - Mention membre dans l'accueil

- Message de bienvenue ajuste pour afficher une vraie mention Discord du membre
  au lieu de son nom texte.
- Validation effectuee sur `Perfect Team Test` avec une instance VPS temporaire
  `TEST_MODE=true`.
- Une base `kayo_test` a ete creee par copie de la base Kayo pour le test, puis
  supprimee pendant le nettoyage de fin de chantier.
- Deploiement production effectue via `tools/vps/deploy-from-git.sh` apres
  checks locaux et nettoyage des ressources temporaires de test.

## 2026-06-11 - Correctif historique MMR Valorant

- PR #27 mergee sur `master` puis deploiement production du commit `36ce7fb`
  via `tools/vps/deploy-from-git.sh`.
- Migration `029_mmr_history_metadata.sql` appliquee en production.
- Verification DB : 8 comptes suivis complets backfilles, 538 lignes Henrik
  avec `match_id`, 0 groupe `match_id` duplique, 0 historique orphelin, 0
  erreur backfill.
- Verification runtime : `kayo-bot` up, `kayo-postgres` healthy, smoke runtime
  OK avec 27 cogs charges.
- Logs recents : backfills MMR termines ; 3 entrees Henrik ignorees sans
  `season.short` ; un 502 Henrik boutique Valorant observe, sans lien avec MMR.

## 2026-06-11 - Notifications boutique Valorant

- Diagnostic production : les erreurs boutique etaient des `HTTP 502 Bad Gateway`
  Henrik sur `/valorant/v2/store-featured`; Kayo restait up.
- Verification Discord production : la notification `Give Back // V26` avait bien
  un fil actif avec 8 messages d'items.
- Correctif valide sur `Perfect Team Test` avec instance VPS temporaire :
  polling boutique a 5 minutes, retry court `15s` puis `45s`, ancien style
  d'embed restaure, footer source retire, fils crees avec 8 items par bundle.
- Deploiement production effectue via `tools/vps/deploy-from-git.sh` sur le
  commit `e88f13c`.
- Verification runtime : `kayo-bot` up, `kayo-postgres` healthy, smoke runtime
  OK avec 27 cogs charges, logs recents sans erreur critique.
- Ressources test nettoyees : `kayo-bot-test`, images test, worktree
  `/tmp/kayo-test-*` et base `kayo_test` supprimes.
- Ajustement supplementaire deploye sur le commit `f5fca78` pour reprendre le
  rendu legacy exact depuis `cogs/_legacy/shop/shop_notifier.py` : titre et
  description en gras, prix total seul, date en footer, image `displayIcon`,
  fil `Détails – ...`, champs item verticaux et `Vente groupée`.
- Verification production apres `f5fca78` : `kayo-bot` up, `kayo-postgres`
  healthy, smoke runtime OK avec 27 cogs charges, logs recents filtres sans
  erreur critique.

## 2026-06-12 - Renvoi notifications boutique Valorant

- Apres validation du rendu sur `Perfect Team Test`, renvoi manuel one-shot des
  notifications boutique sur `Perfect Team` dans le salon `valorant_shop`.
- Aucun changement DB : le one-shot a utilise le presenter deploye et l'API REST
  Discord, sans modifier l'etat `bundle deja envoye`.
- Messages production envoyes :
  - `Give Back // V26` : message/thread `1514770362724778175`, 8 items.
  - `Rogue` : message/thread `1514770395197214843`, 8 items.
- Verification REST apres envoi : titre legacy, description en gras, un seul
  champ prix total, footer date, image presente et 8 embeds d'items par fil.
- Verification runtime : `kayo-bot` up, `kayo-postgres` healthy.

## 2026-06-12 - Correctif fenetre MMR 7 jours

- Diagnostic production read-only : la game `TRG Max#7641` du
  `2026-06-04 11:28 Europe/Paris` etait correctement stockee en DB avec
  `rr_delta=-29`, `match_id` present et source `henrik_stored`.
- Cause : `mmr_track` utilisait `date.today()` cote VPS/UTC et un filtre par
  date calendaire, ce qui incluait tout le `04/06` a `01:48` heure France.
- Correctif deploye sur le commit `548a70e` : fenetre rolling `now - 7 jours`
  en timezone `Europe/Paris`, transmise au calcul MMR, avec baseline graphique
  quand une seule game reste dans la periode.
- Verification locale : tests MMR cibles `33 passed`, `compileall` OK,
  suite pytest complete `242 passed`.
- Verification production apres deploiement : smoke runtime OK avec 27 cogs,
  `kayo-bot` up, `kayo-postgres` healthy, logs recents filtres sans erreur
  critique.
- Reproduction prod apres patch pour `TRG Max#7641` : `7 derniers jours`
  calcule `1` game, total `+19`, moyenne win `+19`, moyenne loss `0`, baseline
  `1800 -> 1819`.

## Suite recommandee

1. Copier automatiquement les backups PostgreSQL hors VPS.
2. Reduire progressivement les permissions Discord du bot.
3. Tester une restauration backup Hostinger ou documenter sa procedure exacte.
