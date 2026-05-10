# Audit Discord live Kayo - 2026-05-10

## Mode d'audit

- Lecture seule via l'API REST Discord avec le token du bot deja present dans le conteneur `kayo-bot`.
- Aucune connexion gateway supplementaire.
- Aucune action Discord destructive.
- Aucun message envoye.
- Aucun role, salon, permission ou commande modifie.
- Aucun token ou secret affiche.

## Bot

- Utilisateur bot: `kayo`
- Bot ID: `1240012983808163940`
- Serveur detecte: `Perfect Team`
- Serveur ID: `1120105855556272219`
- Membres approx.: `81`
- Presences approx.: `15`
- Role le plus haut du bot: `Perfect Team`, position `63`

## Commandes Discord

16 commandes globales sont enregistrees cote Discord:

- `salon`
- `roles`
- `setstatus`
- `mmr_track`
- `clean`
- `moderation`
- `automod`
- `permissions_report`
- `economy`
- `team`
- `matchmaking`
- `reputation`
- `profile_set`
- `profile_show`
- `tournoi`
- `streamer`

Commandes specifiques au serveur: `0`.

Note: les groupes `economy`, `team` et `matchmaking` contiennent leurs sous-commandes dans le code du bot; l'API les expose ici comme commandes globales de type groupe.

## Permissions globales du bot

Le bot a actuellement la permission `administrator` sur `Perfect Team`.

Permissions utiles confirmees:

- voir les salons;
- envoyer des messages;
- envoyer des embeds;
- lire l'historique;
- utiliser les commandes d'application;
- gerer les messages;
- gerer les roles;
- moderer les membres;
- gerer les salons et threads;
- se connecter/parler en vocal.

Manques globaux detectes: aucun.

Remarque securite: `administrator` simplifie l'exploitation du bot, mais augmente le rayon d'impact si le token est compromis. Une reduction en permissions minimales est possible, mais doit etre faite prudemment et avec tests salon par salon.

## Configuration DB comparee a Discord

Comptes DB:

- salons configures: `29`
- roles configures: `37`
- messages persistants: `10`
- configuration automod: `1`

Automod:

- scam detection: active;
- spam detection: active;
- seuil cross-channel spam: `3`;
- fenetre spam: `60s`;
- suppression des messages scam: active.

## Salons configures

Tous les 29 salons/categories/forums/vocaux configures existent encore sur Discord.

Permissions manquantes sur les salons configures: aucune detectee.

Exemples verifies:

- `modération` -> `🛡𝙢𝙤𝙙é𝙧𝙖𝙩𝙞𝙤𝙣`
- `demande-deban` -> `🎫𝙙𝙚𝙢𝙖𝙣𝙙𝙚-𝙙𝙚-𝙙𝙚𝙗𝙖𝙣`
- `deban_category` -> categorie tickets
- `valorant_shop` -> `🛍️𝙗𝙪𝙣𝙙𝙡𝙚-𝙚𝙩-𝙨𝙠𝙞𝙣`
- `rules` -> `📜𝙧𝙚𝙜𝙡𝙚𝙢𝙚𝙣𝙩`
- `rang` -> `🏆𝙧𝙖𝙣𝙜`
- `temp_vocal_lobby` -> `🔈𝙘𝙧𝙚𝙚-𝙪𝙣-𝙫𝙤𝙘𝙖𝙡`

## Roles configures

29 roles configures existent et sont gerables par le bot.

8 roles configures en DB n'existent plus sur Discord:

- `booster` -> `1316143636550910023`
- `chill` -> `1236425387337318482`
- `e-sports` -> `1236426762712383628`
- `rocket league` -> `1236434930842468392`
- `rocket league chill` -> `1236635372432134245`
- `rocket league tryhard` -> `1236635326232006686`
- `tryhard` -> `1236426298805456896`
- `valorant` -> `1236434656866472121`

Impact probable:

- les panneaux ou commandes qui utilisent ces cles ne peuvent pas attribuer ces roles;
- les roles `valorant chill`, `valorant e-sports` et `valorant tryhard` existent encore, donc une partie de la config semble avoir ete migree ou renommee;
- il faut soit supprimer les cles obsoletes, soit les remapper vers des roles Discord actuels.

## Messages persistants

8 messages persistants sont accessibles:

- `demande_deban`
- `embed_rank`
- `queue_status`
- `role_selection`
- `rules_embed`
- `scrim_creation`
- `stats_embed`
- `stats_thread`

2 messages persistants retournent `404`:

- `event` dans le salon `1330349865909227602`, message `1330360063566807132`;
- `vocal_creation` dans le salon `1328536618570612837`, message `1328826964366069852`.

Impact probable:

- si le bot tente de recharger ou mettre a jour ces messages, il peut echouer ou recreer une vue selon la logique du module;
- une commande de reinitialisation ou un nettoyage DB cible peut etre necessaire.

## Commandes executees

Depuis le VPS:

- execution d'un script Python en lecture seule dans `kayo-bot`;
- appels REST Discord:
  - `GET /users/@me`;
  - `GET /users/@me/guilds`;
  - `GET /applications/{application_id}/commands`;
  - `GET /applications/{application_id}/guilds/{guild_id}/commands`;
  - `GET /guilds/{guild_id}`;
  - `GET /guilds/{guild_id}/roles`;
  - `GET /guilds/{guild_id}/channels`;
  - `GET /guilds/{guild_id}/members/{bot_id}`;
  - `GET /channels/{channel_id}/messages/{message_id}` pour les messages persistants.
- requetes SQL read-only:
  - `guild_channel_configs_v2`;
  - `guild_role_configs_v2`;
  - `persistent_messages`;
  - `automod_config`.

## Recommandations

1. Envisager une reduction progressive de la permission `administrator` du bot apres creation d'une matrice de permissions minimales par module.

## Mise A Jour Apres Nettoyage

- Les 8 roles inexistants ont ete supprimes de `guild_role_configs_v2`.
- Les 2 messages persistants `404` ont ete supprimes de `persistent_messages`.
- Backup serveur avant suppression: `/root/kayo-backups/discord-cleanup-20260510014958`.
- Verification apres nettoyage:
  - roles configures restants: `29`;
  - roles obsoletes restants: `0`;
  - messages persistants restants: `8`;
  - messages persistants supprimes restants: `0`;
  - les 8 messages persistants restants repondent `200` via l'API Discord.
