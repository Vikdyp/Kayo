# Architecture

Objectif: separer clairement Discord (UI), logique metier, et acces DB.

## Responsabilites

- cogs/
  - UI Discord uniquement: commands, permissions, embeds, interactions
  - Pas de SQL et pas d'acces DB direct
  - Appelle des services

- database/services/
  - Logique applicative liee a la DB (transactions, orchestration multi-repos)
  - Expose des methodes globales reutilisables par plusieurs cogs

- database/repos/
  - SQL pur + mapping de resultats
  - Aucune logique metier, aucune orchestration

- cogs/<domaine>/services/
  - Logique metier propre au domaine du cog, sans UI Discord
  - Peut appeler database/services/

## Regles cle

- Le SQL reste dans database/repos/.
- Les transactions restent dans database/services/.
- Les cogs restent "UI Discord".
- Les services DB doivent favoriser des methodes globales et reutilisables.
