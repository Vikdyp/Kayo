# Catalogue des comportements Kayo - 2026-05-10

Ce document decrit le comportement actuel du bot pour validation metier. Les libelles Five Stack ont ete corriges: `2`, `3` et `5` signifient maintenant un groupe total de 2, 3 ou 5 joueurs, demandeur compris, et non un `2v2/3v3/5v5`.

## Demarrage Global
-OK

- Le bot ouvre le pool PostgreSQL, applique les migrations, initialise tous les services, charge les cogs, puis synchronise les slash commands.
- En production, les slash commands sont synchronisees globalement. En mode test, elles sont synchronisees sur le serveur de test configure.
- Intents utilises: guilds, members, messages, message content, presences, voice states.
- En cas d'erreur slash command non geree, le bot log l'erreur et tente de repondre en ephemeral avec une erreur interne.
- A la fermeture, le bot ferme le client HTTP et le pool DB.

## Administration

### `/setstatus`
-OK

- Permission par defaut: administrateur.
- Change le statut Discord du bot: `online`, `idle`, `dnd`, `invisible`.
- Change aussi l'activite affichee. Si aucune activite n'est fournie, utilise l'activite par defaut.
- Au demarrage, si aucune presence n'a encore ete definie, le bot se met `online` avec l'activite par defaut.

### `/permissions_report`
-OK

- Permission par defaut: administrateur.
- Genere un CSV des permissions des roles par salon.
- Envoie le fichier en reponse ephemeral.

## Configuration

### `/salon`
-OK

- Permission par defaut: administrateur.
- `status`: affiche les salons attendus et ce qu'il manque.
- `get`: affiche les salons deja configures.
- `set`: associe une cle metier a un salon Discord du serveur courant.
- `remove`: supprime une configuration de salon.
- Autocomplete sur les cles connues.
- Cles importantes: `welcome`, `rules`, `rang`, `modération`, `demande-deban`, `deban_category`, `valorant_shop`, `twitch`, `temp_vocal_lobby`, `temp_vocal_category`, `matchmaking_voice_category`, `teams_forum_id`, `rank_up`, salons de rangs.

### `/roles`
-OK

- Permission par defaut: administrateur.
- `status`: affiche les roles attendus et ce qu'il manque.
- `get`: affiche les roles configures.
- `set`: associe une cle metier a un role Discord du serveur courant.
- `remove`: supprime une configuration de role.
- Autocomplete sur les roles predefinis non encore configures.
- Roles predefinis: reputation, ban, admin, rangs Valorant, roles agents, langues, plateforme.

## Accueil Et Statistiques Membres

### Message de bienvenue
-OK

- Listener: `on_member_join`.
- A chaque arrivee, le bot lit les salons `welcome`, `rules`, `introductions`.
- Si `welcome` est configure et trouvable, il envoie un embed de bienvenue.
- Si les salons de regles/presentation manquent, le texte de bienvenue utilise un libelle generique.

### `!embed_statistique`
-OK

- Commande prefix.
- Permission: administrateur.
- Cree ou force la creation de l'embed de statistiques membres dans le salon stats configure.
- Sauvegarde le message en DB.
- Cree un thread "Notifications departs" attache au message et le sauvegarde en DB.
- Repond dans le salon avec un message temporaire de confirmation.

### Embed stats persistent
-OK

- Au demarrage, le bot recharge le message stats sauvegarde et rattache les boutons.
- Boutons disponibles: mettre a jour, 7 jours, 1 mois, 1 an, total.
- Les boutons regenerent l'embed et le graphique sur la periode demandee.
- Tache quotidienne a minuit Europe/Paris: met a jour l'embed stats pour chaque serveur.
- Listener `on_member_join`: enregistre l'arrivee dans les stats.
- Listener `on_member_remove`: enregistre le depart et envoie une notification dans le thread configure si present.

## Moderation

### `/clean`
-Corrige: toutes les suppressions `/clean` demandent confirmation.

- Permission: administrateur.
- Fonctionne seulement dans un salon texte.
- `all`: demande confirmation, puis supprime jusqu'au maximum scanne par le service.
- `user`: demande confirmation, puis supprime les messages de l'utilisateur cible.
- `number`: demande confirmation, puis supprime les N derniers messages, avec limite max.
- `from`: demande confirmation, puis supprime les messages apres un ID de message.
- `image`: demande confirmation, puis supprime les messages avec pieces jointes image.
- `gif`: demande confirmation, puis supprime les messages avec GIF ou contenu contenant `gif`.
- `links`: demande confirmation, puis supprime les messages contenant une URL.
- `history`: affiche les 50 dernieres suppressions; si trop long, envoie un fichier texte.
- Les suppressions avec confirmation utilisent des boutons confirmer/annuler.

### `/moderation`
-OK: `warn` n'applique pas de ban automatique. Il n'y a pas de maximum configure actuellement.

- Permission par defaut: administrateur, et verification interne `ban_members`.
- Actions: `ban`, `unban`, `warn`, `check_status`.
- `ban`: cible obligatoire, raison obligatoire, duree optionnelle. Applique un ban interne via role `ban`, sauvegarde les roles restaurables, supprime les roles sur tous les serveurs ou le membre est present, enregistre le ban en DB et envoie un DM si possible.
- Ban temporaire: si `duration_minutes` est fourni, un `ban_end` est stocke.
- Suppression de messages au ban: options `none`, `1h`, `6h`, `12h`, `24h`, `7d`; scope `current` ou `all`.
- `unban`: cible obligatoire. Retire le role `ban`, restaure les roles sauvegardes par serveur, supprime le ban interne en DB, envoie un DM si possible.
- `warn`: ajoute un avertissement en DB et envoie/log selon le service.
- `check_status`: affiche le statut moderation interne de l'utilisateur.

### Enforcement des bans internes
-OK

- Listener `on_member_join`: si un membre revient avec un ban interne actif, le bot reapplique le role `ban`.
- Listener `on_member_update`: si les roles changent ou si l'onboarding se termine, le bot verifie et reapplique un ban interne actif.
- Tache chaque minute: verifie les bans temporaires expires et debannit automatiquement.

### `/automod`
-OK

- Permission par defaut: administrateur.
- `status`: affiche la configuration automod.
- `enable_scam` / `disable_scam`: active/desactive la detection scam.
- `enable_spam` / `disable_spam`: active/desactive la detection spam multi-salons.
- `spam_config`: modifie le seuil de salons `2-10` et/ou la fenetre `10-300s`.
- `add_role` / `remove_role`: ajoute/retire un role de la whitelist automod.
- `add_channel` / `remove_channel`: ajoute/retire un salon de la whitelist automod.
- `add_pattern` / `remove_pattern` / `list_patterns`: gere les regex scam personnalisees.
- `add_domain` / `remove_domain` / `list_domains`: gere les domaines scam personnalises.
- La configuration est mise en cache et invalidee apres mutation.

### Automod sur messages
-Corrige: apres une alerte spam, les messages suivants avec le meme contenu sont supprimes pendant la fenetre de traitement, et le bouton `Bannir` recharge les references recentes avant suppression.

- Listener `on_message`.
- Ignore les DM, les bots, les webhooks, les membres/salons whitelistes.
- Si scam active: detecte contenu/domaines/patterns scam. En cas de detection, timeout temporaire si possible, supprime le message, applique un ban interne permanent, DM l'utilisateur si possible, log dans le salon moderation.
- Si spam active: detecte le meme contenu poste dans plusieurs salons selon seuil/fenetre.
- En cas de spam, envoie une alerte moderation avec boutons.

### Alerte spam
-OK

- Bouton `Bannir`: exige `ban_members` ou `administrator`, supprime les messages references, applique un ban interne permanent, DM l'utilisateur si possible, marque l'alerte comme traitee.
- Bouton `Ignorer`: exige `ban_members` ou `administrator`, ajoute l'utilisateur a une whitelist spam temporaire de 24h, marque l'alerte comme ignoree.
- Une alerte deja traitee refuse les actions suivantes.

### `!send_deban`
-Permission admin?

- Commande prefix.
- Permission: administrateur.
- Cree le panneau principal de demande de deban dans le salon `demande-deban`.
- Refuse s'il existe deja un panneau persistant.
- Sauvegarde le message en DB et rattache la vue au redemarrage.

### Demandes de deban
-Permission ok?

- Bouton du panneau: ouvre un formulaire avec la raison.
- Refuse si l'utilisateur a deja une demande en attente.
- Refuse si l'utilisateur n'est pas actuellement banni.
- Cree un salon prive dans `deban_category` visible par le demandeur, le bot et le role `admin`.
- Poste un embed de demande avec boutons `Accepter` / `Refuser`.
- `Accepter`: exige `ban_members`, appelle le deban interne, marque la demande acceptee et supprime le salon.
- `Refuser`: exige `ban_members`, DM l'utilisateur si possible, marque la demande refusee et supprime le salon.
- Au demarrage, le bot recharge les vues persistantes du panneau et des demandes en attente.

## Economie
-Toute la partie eco n'est pas utile mais je vais quand meme review on pourra desactiver.

### `/economy daily`
-OK

- Donne les pieces quotidiennes a l'utilisateur.
- Refuse si deja reclame le meme jour.
- Le montant peut dependre des roles via le service.

### `/economy shop`
-OK

- Affiche la boutique du jour en ephemeral.
- Les boutons `Acheter ...` tentent l'achat de l'objet.
- Si la balance est insuffisante, le bot refuse l'achat.
- La boutique est regeneree une fois par jour.

### `/economy inventaire`
-OK

- Affiche le profil economie et l'inventaire de l'utilisateur.

### `/economy trade`
-OK

- Lance un echange public entre deux membres.
- Refuse l'auto-echange, les bots et les noms d'item vides.
- Les deux utilisateurs concernes doivent cliquer `Confirmer`.
- Quand les deux ont confirme, le service transfere l'item si le proposant le possede encore.

## Five Stack

### `!start_queue`
-OK

- Commande prefix.
- Permission: administrateur.
- Envoie le message de recherche Five Stack avec boutons `Solo`, `Equipe`, `Quitter`.
- Sauvegarde le message en DB pour rechargement au redemarrage.

### Boutons de recherche
-OK

- `Solo`: ouvre un select de taille de groupe.
- `Equipe`: ouvre le meme select mais utilise l'equipe creee par `/team create`.
- Options:
  - `Any`: le bot choisit la meilleure taille disponible.
  - `Duo`: cherche a former un groupe total de 2 joueurs, demandeur compris.
  - `Groupe de 3`: cherche a former un groupe total de 3 joueurs, demandeur compris.
  - `Equipe de 5`: cherche a former un groupe total de 5 joueurs, demandeur compris.
- Le bot refuse si le compte Valorant n'est pas lie.
- En mode equipe, seul le leader d'une equipe existante peut rejoindre.
- Le message de queue est rafraichi apres inscription/desinscription.

### Matching automatique
-OK

- Tache toutes les 15s.
- Groupe les entrees compatibles par serveur, langue, region et plateforme.
- Essaie de former un groupe de 5, puis 3, puis 2.
- Une entree `Any` peut rentrer dans n'importe quelle taille.
- Une entree ciblee ne rentre que dans sa taille cible.
- Le total de membres doit exactement atteindre la taille cible.
- A la creation d'un groupe, le bot cree un salon vocal prive `Five Stack N joueurs`, enregistre le match et DM les participants.

### Vieillissement de la queue
-OK

- Tache chaque minute.
- Apres 5 minutes, une entree ciblee passe en `Any`.
- Apres 10 minutes, l'entree expire et l'utilisateur recoit un DM si possible.

### Equipes Five Stack
-OK

- `/team create`: cree une equipe publique ou privee, si l'utilisateur a un profil Valorant et n'est pas deja dans une equipe. Cree un thread forum si `teams_forum_id` pointe vers un forum.
- `/team join`: rejoint une equipe par code, si l'utilisateur a un profil Valorant et n'est pas deja dans une autre equipe.
- `/team leave`: quitte l'equipe. Si l'equipe devient vide, le bot supprime les ressources.
- `/team kick`: seul le leader peut retirer un membre. Le leader ne peut pas se kick lui-meme.
- `/team delete`: seul le leader peut supprimer l'equipe et ses ressources.
- `/team list`: liste jusqu'a 20 equipes actives.
- `/team info`: affiche l'embed d'une equipe.
- Listener `on_member_remove`: si le leader quitte le serveur, l'equipe est supprimee; sinon le membre est retire.
- Tache horaire: supprime les equipes plus vieilles que 24h et leurs ressources.

### Stats Five Stack
-OK

- `!role_counters`: affiche les compteurs par role Valorant dans la queue.
- `/matchmaking stats`: stats d'un membre, ou de soi par defaut.
- `/matchmaking history`: historique global ou historique d'un membre, limite 1-25.
- `/matchmaking server`: statistiques serveur et distribution par taille de groupe.
- `/matchmaking leaderboard`: classement par nombre de matchs ou temps d'attente.
- `/matchmaking feedback`: enregistre une note 1-5 et commentaire optionnel pour un match.
- Tache toutes les 5 minutes: supprime les vocaux vides dans la categorie `voice_cleaner_category`, sauf `voice_cleaner_afk`.

## File Counter

### `!init_counter`
-OK

- Commande prefix.
- Permission: administrateur.
- Utilise le salon configure `file_counter`.
- Supprime l'ancien compteur actif si possible.
- Envoie un embed avec deux boutons et sauvegarde le message actif.

### Boutons compteur
-OK

- `Ajouter`: incremente le compteur de fichiers ajoutes.
- `Terminer`: incremente le compteur de fichiers termines.
- Refuse si le message clique n'est plus le compteur actif.
- Met a jour l'embed du compteur.

## Fun

### Reponse "quoi"
-OK

- Listener `on_message`.
- Ignore bots et DM.
- Si un message finit par un trigger reconnu de type `quoi`, repond avec une reponse aleatoire et l'emoji `pepe_clown` si disponible.
- Le service applique un anti-spam/cooldown par utilisateur.

## Reputation Et Profil

### `/reputation`
-OK

- Disponible sans permission admin.
- `view`: affiche le resume reputation du membre cible.
- `report`: signale un membre avec raison optionnelle. Refuse l'auto-signalement, les doublons journaliers et les limites du service.
- `recommend`: recommande un membre. Refuse l'auto-recommandation, les doublons journaliers et les limites du service.
- Apres report/recommend, le bot synchronise les roles de reputation configures (`bon joueur`, `mauvais joueur`, etc.) si possible.

### `/profile_set`
-OK

- Enregistre ou met a jour le profil utilisateur: genre, lien tracker Valorant, LFT/equipe, note.
- Valide via le service, notamment les liens et champs interdits.

### `/profile_show`
-OK

- Affiche le profil complet du membre cible, ou soi par defaut.
- Inclut reputation, profil, rang detecte par role, langue et plateforme detectees par roles.

## Roles Et Regles

### `!setup_roles`
-OK

- Permission: administrateur.
- Verifie que les roles agent Valorant sont configures et existent.
- Envoie ou met a jour un panneau persistant avec boutons: Initiator, Controller, Duelist, Sentinel, Fill.
- Un clic rend la selection exclusive: retire les autres roles agent configures et ajoute le role choisi.
- Met a jour les compteurs de l'embed apres changement.

### `!setup_language`
-OK (non utiliser)

- Permission: administrateur.
- Verifie les roles de langue configures.
- Envoie ou met a jour un panneau persistant avec boutons: Francais, Anglais, Espagnol.
- Un clic toggle le role de langue choisi, sans exclusivite stricte entre langues.

### `!setup_rules`
-OK

- Permission: administrateur.
- Utilise le salon configure `rules`.
- Envoie ou met a jour l'embed de reglement avec le bouton `Accepter le reglement`.
- Le bouton enregistre l'acceptation en DB.
- Si l'utilisateur a deja accepte, le bot le signale.

## Scrims

### `!init_scrim`
-OK

- Commande prefix.
- Permission: administrateur.
- Envoie le panneau persistant de creation de scrim.
- Sauvegarde le message en DB.

### Creation et participation scrim
-OK

- Bouton `Creer un scrim`: ouvre un modal date, heure, map, rang, notes.
- L'utilisateur doit avoir accepte le reglement.
- Format attendu: `JJ/MM/YYYY` et `HH:MM`.
- Le bot cree le scrim en DB puis poste un embed avec boutons.
- Boutons `Rejoindre Equipe 1`, `Rejoindre Equipe 2`: inscrivent l'utilisateur dans l'equipe choisie si les regles sont acceptees.
- Bouton `Quitter le scrim`: retire l'utilisateur du scrim.
- Le message est edite apres chaque join/leave.
- Tache chaque minute: quand l'heure de debut arrive, le bot supprime le message, DM les participants si possible et marque le scrim complete.
- Au demarrage, les vues persistantes sont rechargees.

## Valorant Rank Et MMR

### `!send_embed_rang`
-OK

- Permission: administrateur.
- Envoie le panneau persistant de liaison Valorant dans le salon `rang`.
- Refuse si le panneau existe deja et que le message est encore present.
- Sauvegarde le message en DB.

### Boutons Valorant
-OK

- `Renseigner Pseudo/Tag Valorant`: ouvre un modal pseudo/tag.
- `Changer de compte Valorant`: exige un compte deja lie, puis ouvre le modal.
- `Effacer mes donnees Valorant`: supprime les donnees Valorant de l'utilisateur.
- Le modal refuse pseudo vide et tag non alphanumerique.
- Si le pseudo/tag existe deja chez un autre utilisateur, refuse et notifie les moderateurs via `duplicate_alert`, puis `moderation`, puis `rank_up` en fallback.

### Pipeline de rang
-OK

- Au demarrage, le bot recharge le panneau et synchronise la presence: utilisateurs presents actifs, absents inactifs.
- Tache toutes les 5s: traite jusqu'a 20 utilisateurs actifs a mettre a jour.
- Interroge HenrikDev, met a jour PUUID, region, plateforme, rang, elo, saison/act.
- Si le rang change, retire les anciens roles de rang configures et ajoute le nouveau.
- Ignore les membres absents ou ayant le role `ban`.
- En cas de rate limit Henrik/local, ralentit temporairement la boucle.
- En cas d'erreurs persistantes, DM l'utilisateur au maximum une fois tous les 7 jours.

### `/mmr_track`
-OK

- Exige un compte Valorant lie.
- `activer`: active le suivi MMR et recupere l'historique complet.
- `desactiver`: desactive le suivi.
- `afficher`: affiche les stats et un graphique pour `today`, `week`, `all` ou une partition episode/act.
- Autocomplete sur `periode`: aujourd'hui, 7 jours, total, et partitions disponibles.
- Tache toutes les 5 minutes: enregistre un snapshot MMR courant pour les joueurs suivis.

### Notifications de rank up/down
-OK mais on pourrait rendre ca mieux on sait quand le membre change de role c'est le bot qui le fait la on detecte une de nos action au lieu de le faire passer en interne par exemple.

- Listener `on_member_update`.
- Observe uniquement les remplacements de roles de rang configures.
- Attend une suppression puis un ajout de role dans une fenetre de 2s pour eviter les faux positifs.
- Envoie un message dans `rank_up` avec ancien rang, nouveau rang et percentile estime.

### Compteurs de rangs en ligne
-OK

- Listener `on_presence_update`: quand un membre passe online/offline, rafraichit les compteurs de ses rangs.
- Tache toutes les 10 minutes: rafraichit tous les salons compteurs de rangs.
- Renomme les salons selon le nombre de membres non offline dans chaque role de rang.
- Rate limiter interne pour eviter trop de renommages.

## Valorant Shop
-OK mais je preferais l'ancien affichage

- Tache toutes les 30 minutes si `HENRIK_VALO_KEY` est configure.
- Recupere les bundles featured via HenrikDev.
- Pour chaque serveur avec salon `valorant_shop`, filtre les bundles non encore envoyes.
- Envoie un embed bundle, cree un thread detail si le bundle a des items, puis poste chaque item dans le thread.
- Marque chaque bundle envoye en DB pour eviter les doublons.
- En cas de rate limit ou erreur API, log et saute le cycle.

## Tournois

### `/tournoi`
-OK

- Permission: administrateur.
- `create`: si aucun tournoi actif, ouvre un modal de creation.
- `close`: ferme le tournoi actif si present.
- Le code accepte encore l'ancienne valeur `creat` par securite, mais le choix Discord affiche maintenant `create`.

### Creation et inscription tournoi
-Ok mais a revoir plus propre

- Modal creation: nom, nombre max d'equipes, debut inscriptions, fin inscriptions, date tournoi.
- Format date attendu: `JJ/MM/YYYY HH:MM`.
- Poste l'embed tournoi dans le salon d'inscription configure, sinon dans le salon courant.
- Bouton `S'inscrire au tournoi`: ouvre un modal equipe.
- Modal equipe: nom d'equipe, exactement 5 IDs joueurs, extras optionnels.
- Refuse si tournoi complet, equipe doublon ou tournoi non actif.
- Publie l'equipe dans le salon public configure si present.
- DM les joueurs inscrits si possible.
- Au demarrage, recharge la vue du tournoi actif.

## Twitch

### `/streamer`
-OK

- Permission par defaut: administrateur.
- `add`: ajoute un streamer a surveiller.
- `remove`: retire un streamer.
- `list`: liste les streamers configures.
- Si les credentials Twitch manquent, la boucle de notification est desactivee.

### Notifications live
-OK

- Tache chaque minute si Twitch est configure.
- Pour chaque serveur avec salon `twitch`, recupere les streamers configures.
- Interroge Twitch pour les streams live, infos utilisateur, followers et image du jeu.
- Envoie une notification uniquement au passage offline -> live.
- Le message contient un embed et un bouton lien vers Twitch.

## Vocaux Temporaires

### Creation automatique
-OK

- Listener `on_voice_state_update`.
- Necessite `temp_vocal_lobby` et `temp_vocal_category`.
- Quand un membre rejoint le lobby, le bot cree un vocal temporaire dans la categorie configuree.
- Le bot deplace le membre dans le nouveau vocal.
- Le nom est construit a partir du nom d'affichage du membre.
- Avant creation, le bot supprime les doublons vides portant le meme nom.

### Nettoyage vocaux temporaires
-OK

- Si un vocal temporaire devient vide, il est programme pour suppression apres 5 minutes.
- Si quelqu'un rejoint avant la fin du delai, la suppression est annulee.
- Tache chaque minute: rescane les vocaux temporaires pour programmer/annuler les suppressions oubliees.

## Points A Valider

- `/reputation report` est accessible a tous les membres: a confirmer si c'est voulu. - OK
- `!ping` est accessible a tous: a confirmer. - Corrige: administrateur uniquement
- `!role_counters` est accessible a tous: a confirmer. - Corrige: administrateur uniquement
- `/tournoi` utilise l'action `creat` au lieu de `create`: a confirmer si on corrige. - Corrige: `create`
- Le bot a `administrator` sur Discord: fonctionnel, mais large en impact securite. - OK
- Les actions `/clean image`, `/clean gif`, `/clean links` suppriment sans confirmation supplementaire, contrairement a `all/user/number/from`. - Corrige
- L'automod scam applique un ban interne permanent immediat. - OK


Remarque global:

-Ajouter une verification du reglement sur toute les commande et tout interaction avec le bot
-Les commande avec option ne doivent pas cree plusieurs commande comme /matchmaking stats, /matchmaking history, /matchmaking server, /matchmaking leaderboard, /matchmaking on veux le minimum de commande possible temps que ca reste claire et des commande avec option exemple matchmaking avec option history serveur leaderboard etc applique ca pour toute les commande du bot

Etat:
- A traiter en chantier transverse: verification reglement centralisee sur les commandes/interactions utilisateur, avec exemptions staff/setup/deban a definir proprement.
- A traiter en chantier transverse: rationalisation des slash commands en commandes a option unique quand c'est plus clair, sans casser les commandes existantes sans phase de transition.
