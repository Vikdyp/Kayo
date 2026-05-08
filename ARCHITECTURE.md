# Guide de développement

## Objectif

Séparer clairement :

- UI Discord (cogs)
- Logique métier (services)
- Accès base de données (repos/services DB)
- Intégrations externes

Le but est d’obtenir un code maintenable, testable et scalable.

---

## Structure et responsabilités

### cogs/

- UI Discord uniquement
- Commands, permissions, embeds, interactions
- Aucun accès DB
- Aucun appel SQL
- Appelle uniquement des services métier

### cogs/<domaine>/services/

- Logique métier du domaine
- Validation des entrées
- Orchestration applicative
- Appelle services DB et integrations
- Un cog peut contenir plusieurs services
- **Interdit : SQL, `utils.database`, `asyncpg`, `database/repos`**

### database/repos/

- SQL pur + mapping
- Un repo = une table
- Aucun appel à un autre repo
- Aucune logique métier

### database/services/

- Gestion des transactions
- Orchestration multi-repos
- Règles métier liées à la DB
- Méthodes globales réutilisables

### integrations/

- Clients HTTP
- Modèles Pydantic
- Gestion des erreurs API
- Aucun accès DB

### core/

- Assemblage runtime
- Injection des services
- Aucun SQL
- Aucun code Discord UI

---

## Règles clés

- Le SQL reste dans `database/repos/`
- Les transactions restent dans `database/services/`
- Les cogs sont UI uniquement
- Les services métier ne contiennent aucun accès DB
- Les services DB doivent être réutilisables
- Async partout

---

## Base de données et transactions

### Règles

- Transactions uniquement dans `database/services/`
- Interdiction d’ouvrir une transaction ailleurs
- Un repo ne peut pas appeler un autre repo
- Séparation stricte read/write

### Convention

Read:
- get_*
- fetch_*
- list_*

Write:
- create_*
- update_*
- delete_*

Interdit de mixer read/write.

### Nommage

- Repo: `<table>_repo.py`
- Service DB: `<domaine>_service.py`

---

## Migrations

### Principe

- Fichiers SQL dans `database/migrations/`
- Historique dans `schema_migrations`
- Une migration = une transaction

### Convention

Format:

001_description.sql  
002_add_index.sql  

Règles:

- Numérotation unique
- Pas de modification après déploiement
- Nouvelle migration obligatoire pour corriger

### Bonnes pratiques

- IF EXISTS / IF NOT EXISTS
- Index explicites
- Migrations courtes
- Pas de schéma hybride non documenté

---

## Modèles & validation

### Catégories

1) InputModel (entrée Discord)
2) DomainModel (métier)
3) DbRowModel (DB)

### Règles

- Validation dans les services de cog
- Pas dans les cogs
- Repos retournent des modèles
- Mapping dans le repo
- Pas de dict brut hors repos

### Organisation

cogs/<domaine>/models.py  
database/models.py

---

## Gestion des erreurs & UX Discord

### Principes

- Pas d’exception brute
- Transformation par couche
- Embed standard pour l’utilisateur

### Format

- error_id
- code (optionnel)
- message court

### Mapping

Repo → erreurs techniques  
Service DB → erreurs applicatives  
Service cog → erreurs utilisateur  
Cog → affichage

### Logs

- error_id obligatoire
- Contexte si pertinent
- Pas de secrets

---

## Observabilité et logs

### Logger

- logging standard
- Un logger par module

### Niveaux

- debug: interne
- info: événements
- warning: anomalie récupérable
- error: erreur gérée
- exception: stacktrace

### Contexte

- guild_id
- user_id
- command_name

Si pertinent uniquement.

---

## Tâches périodiques

### Règles

- Centralisées ou clairement identifiées
- Nom explicite
- try/except obligatoire
- Logs start/stop
- Pas de while True non contrôlé

### Accès DB

- Via services DB
- Pagination obligatoire
- Batch processing

### API

- Respect rate limits
- Backoff simple
- Skip si down

### Discord

- Vérifier avant update
- Batch si possible
- Pas de spam endpoints

---

## Rate limiting & anti-spam

### Cooldown

Obligatoire pour commandes coûteuses.

Par défaut:

- Simple: 1 / 2s
- DB: 1 / 5s
- API: 1 / 10s

### Implémentation

- @commands.cooldown
- Définition dans les cogs

### Exceptions

- Admins
- Commandes internes

---

## Tests & qualité

### Framework

- pytest

### Priorités

1) Services DB
2) Services métier
3) Intégrations
4) Utils

### Règles

- Feature critique = tests minimaux
- Nominal + erreur
- Pas d’API réelle en test

### Dette

- Zones non testées documentées
- Refactor = tests prioritaires

---

## Réutilisation et rationalisation

### Principe

Avant de supprimer ou recréer une fonctionnalité :

1) Identifier l’existant (legacy ou partiel)
2) Évaluer son utilité réelle
3) Si utile :
   - migrer vers la nouvelle architecture
   - créer repo + service DB + service métier
4) Éviter les doublons fonctionnels

Interdit :

- Supprimer une feature sans analyse
- Recréer une feature existante sous un autre nom
- Dupliquer des systèmes similaires

Objectif :

- Un seul mécanisme par besoin fonctionnel
- Réutilisable par plusieurs domaines

---

## Workflow de développement

### Nouvelle feature

1. Analyse
2. Vérification existant
3. Migration si nécessaire
4. Repo → Service DB → Service cog → Cog
5. Logs/erreurs
6. Tests si critique
7. Cooldown/perf

### Refactor

- Objectif écrit
- Petites étapes
- Tests si critique
- Pas de déplacement de SQL vers services métier

Interdit: refactor massif aveugle.

### Suppression

1. Vérifier usages
2. DB/migrations
3. Tests
4. Imports
5. Doc

---

## Dette technique

### TODO

Format obligatoire:

TODO(date, priorité): description

### Revue

- Mensuelle
- Nettoyage
- Simplification
- Optimisation

### Priorité

La dette bloquante prime.

---

## Discipline

### Anti-flou

Interdit:

- souvent
- en général
- ça dépend

Autorisé:

- toujours
- jamais
- max/min chiffré
