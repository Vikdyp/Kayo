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

## Suite recommandee

1. Copier automatiquement les backups PostgreSQL hors VPS.
2. Reduire progressivement les permissions Discord du bot.
3. Ajouter une alerte externe sur crash ou redemarrages repetes.
