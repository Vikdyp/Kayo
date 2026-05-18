# AGENTS.md

Instructions locales pour Codex et les autres agents de code travaillant sur
Kayo. Ce fichier doit rester pratique, court et specifique au projet. Ajouter
une regle seulement si elle evite une erreur reelle ou clarifie une decision
importante.

## Contexte Projet

Kayo est un bot Discord Python base sur `discord.py`.

- Serveur principal : `Perfect Team`.
- Serveur de test : `Perfect Team Test`.
- Communaute : principalement francophone, avec des membres anglophones ou
  hispanophones possibles.
- Origine produit : faciliter la recherche de teammates Valorant.
- Direction produit : Kayo peut evoluer vers d'autres fonctionnalites utiles a
  la communaute, mais l'axe Discord, Perfect Team et Valorant reste central.
- Production : VPS avec Docker.
- Branche de production : `master`.

## Langue Et Style

- Repondre a Victor en francais.
- Garder les identifiants de code, classes, fonctions, modules et commits dans
  le style existant du depot, generalement en anglais.
- Les textes visibles dans Discord sont en francais par defaut.
- Si une fonctionnalite s'adresse naturellement a des membres non francophones,
  proposer une strategie multilingue avant de l'implementer.
- Ecrire clairement les changements visibles Discord dans la reponse finale pour
  que Victor sache quoi tester.

## Sources Locales

Lire seulement les documents utiles a la tache.

- Vue d'ensemble et setup : `README.md`
- Architecture : `docs/ARCHITECTURE.md`
- Operations, deploiement, rollback, incident : `docs/RUNBOOK.md`
- Historique operations : `docs/OPERATIONS_LOG.md`
- Direction DB v2 et contraintes migrations : `docs/DATABASE_V2_PROPOSAL.md`
- CI : `.github/workflows/ci.yml`
- Smoke runtime : `tools/smoke_runtime.py`

Pour une tache normale, commencer par `README.md`, `docs/ARCHITECTURE.md`, puis
les fichiers d'implementation et tests concernes.

## Methode De Travail

Victor dirige le projet et garde le dernier mot sur le produit, les priorites,
l'UX Discord, les donnees et la production.

Avant une tache de code, cadrer brievement :

- objectif
- besoin compris
- hypotheses utiles
- scope et non-objectifs
- risques principaux
- validation prevue

Pour une petite correction evidente, garder ce cadrage court. Pour une feature,
un refactor significatif, une migration ou un incident, detailler davantage le
plan avant d'agir.

Chercher la cause avant de corriger un bug, surtout si le bug touche Discord,
la base de donnees, la production ou plusieurs modules.

## Autonomie Autorisee

Codex peut, sans validation prealable :

- lire le code et les docs locales utiles
- modifier des fichiers localement dans le scope valide
- lancer les checks pertinents
- ajouter une dependance justifiee si elle reste reversible et documentee
- corriger une faiblesse proche du changement quand cela reduit le risque
- mettre a jour la doc liee quand le comportement, la configuration ou la
  procedure change

Rester pragmatique : avancer sans demander pour chaque micro-action, mais
expliquer les choix importants.

## Validation Obligatoire

Demander validation explicite avant :

- toute action VPS, production, deploiement ou rollback
- toute migration DB ou operation risquee sur les donnees
- toute suppression destructive ou changement difficilement reversible
- tout changement important d'UX Discord
- tout changement de roles, permissions, salons, moderation, messages publics ou
  notifications
- tout changement de securite
- tout ajout ou changement d'API externe, service payant, quota, token ou cout
- tout changement d'architecture structurant
- toute creation de branche, commit, push ou pull request, sauf demande claire
  de Victor

Si un risque serieux apparait en cours de tache, s'arreter et demander
validation quand il touche DB, prod, securite ou UX Discord importante. Sinon,
choisir la solution prudente et l'expliquer.

## Donnees, Secrets Et Fichiers Sensibles

- Ne pas modifier ni committer `.env*`, secrets, logs, dumps, backups, exports
  de donnees ou etat runtime.
- Ne pas afficher de donnees utilisateur reelles sans raison claire.
- Les donnees locales peuvent etre inspectees si necessaire.
- Les donnees VPS ou production demandent une validation explicite.
- Ne jamais appeler de vraies APIs externes depuis les tests.

## Architecture Et Qualite

Suivre l'architecture du depot, mais ne pas copier une mauvaise base quand elle
augmente le risque. Ameliorer proprement dans le perimetre de la tache.

Regles importantes :

- `cogs/` contient l'UI Discord : commandes, permissions, embeds, vues et
  interactions.
- `cogs/*/services/` contient la logique metier et la validation.
- `database/services/` contient transactions et orchestration multi-repos.
- `database/repos/` contient SQL pur et mapping des lignes.
- `integrations/` contient les clients HTTP et modeles d'API.
- `core/` contient l'assemblage runtime et l'injection de services.
- Un service metier sous `cogs/*/services/` ne doit pas importer
  `database.repos` ni `asyncpg`.
- Les cogs ne doivent pas acceder directement a la DB.
- Ne pas reactiver `cogs/_legacy/` sans migration vers l'architecture actuelle.

Dette technique :

- Corriger la dette proche et raisonnable quand elle sert la tache.
- Mentionner la dette plus large en fin de tache ou proposer une issue separee.
- Ne pas melanger un gros nettoyage hors scope avec une correction simple.

## Discord Et Tests Serveur

Pour tout changement visible Discord :

1. Valider techniquement en local quand c'est possible.
2. Indiquer clairement ce qui doit etre teste sur `Perfect Team Test`.
3. Ne pas envisager `Perfect Team` avant retour ou validation de Victor.

Tester le rendu Discord reel sur le serveur de test quand les permissions,
salons, boutons, embeds, commandes slash, messages publics ou notifications sont
concernes.

## Base De Donnees

Les migrations doivent etre forward-only et additives sauf plan valide separe.

Pour toute migration ou changement persistance :

- proposer le plan avant implementation
- penser backup et rollback
- ne pas modifier une migration deja appliquee pour corriger l'historique
- ajouter une nouvelle migration si le travail DB est explicitement dans le
  scope
- tester localement ou sur environnement de test avant toute production
- demander validation explicite avant action production

## Git

- Pour les petits changements, rester sur la branche courante sauf instruction
  contraire.
- Pour une tache importante, proposer une branche dediee.
- Ne pas commit, push ou ouvrir de PR sans validation explicite.
- Ne jamais revert des changements non faits par Codex sans demande claire.
- Ignorer les changements locaux non lies a la tache.

## Checks

Adapter les checks au risque.

Commandes de reference :

```bash
python -m compileall -q bot.py core cogs database integrations tests tools
python -m pytest -q
python tools/smoke_runtime.py
```

CI lance actuellement :

```bash
python -m compileall -q bot.py core cogs database integrations tests tools
python -m pytest -q
```

Reperes :

- Documentation seule : relecture et diff suffisent generalement.
- Petite correction isolee : test cible ou compile si pertinent.
- Feature, refactor, DB, release : compile, pytest complet, puis smoke runtime
  si l'environnement le permet.
- Production : suivre `docs/RUNBOOK.md`; utiliser `--skip-migrations` seulement
  si le runbook ou l'objectif le demande.

## Incidents Production

Si Victor signale un bug production :

1. Diagnostiquer avant de corriger.
2. Lire logs et etat Docker selon `docs/RUNBOOK.md` si l'acces est autorise.
3. Lancer un backup avant toute action DB.
4. Proposer un patch minimal.
5. Valider localement ou sur `Perfect Team Test` quand possible.
6. Demander validation avant deploiement ou rollback.
7. Noter l'action dans `docs/OPERATIONS_LOG.md` si la production change.

## Definition Of Done

Une tache est terminee quand :

- le scope est respecte
- le comportement runtime n'a change que si demande
- les changements visibles Discord sont listes
- les checks pertinents sont passes ou expliques comme non lances
- la doc durable est mise a jour seulement si la realite projet change
- aucun secret, log, dump, backup ou etat runtime n'est ajoute
- les risques restants sont explicites

La reponse finale doit contenir :

- fichiers changes
- resume
- validations lancees
- validations non lancees avec raison
- risques restants
- prochaine etape concrete
