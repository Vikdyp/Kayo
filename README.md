# KayoBot

![Logo du Bot](path/to/your/logo.png)

## Description

**KayoBot** est un bot Discord développé en Python utilisant la bibliothèque `discord.py`. Il offre une variété de fonctionnalités pour gérer les salons, les rôles, les scrims, les rapports et bien plus encore. Grâce à une architecture modulaire basée sur des cogs, KayoBot est extensible et facile à maintenir.

## **Fonctionnalités**

- **Gestion des Messages** : Nettoyage des messages dans les salons.
- **Heartbeat** : Envoi régulier de messages pour maintenir l'activité du bot.
- **Gestion des Rangs** : Attribution de rôles basés sur les rangs des utilisateurs dans Valorant.
- **Système de Signalement** : Signalement et recommandation des utilisateurs avec gestion des rôles associés.
- **Gestion des Rôles** : Attribution automatique de rôles basés sur les combinaisons de rôles existants.
- **Gestion des Scrims** : Inscription, création de salons vocaux, suivi des résultats.
- **Gestion des Salons Vocaux** : Listage, rejoindre et création de salons vocaux temporaires.
- **Sauvegarde des Rôles** : Sauvegarde et restauration des configurations de rôles.
- **Économie Virtuelle** : Système de monnaie, récompenses quotidiennes, et transactions.
- **Modération Avancée** : Commandes de modération telles que le bannissement permanent.
- **Classement des Membres** : Suivi et affichage des statistiques des membres.

## **Prérequis**

- **Python** : Version 3.8 ou supérieure
- **Bibliothèques Python** :
  - `discord.py` (version 2.1.0+)
  - `aiofiles`
  - `python-dotenv`
  - Autres dépendances listées dans `requirements.txt`
- **Un bot Discord** avec les permissions nécessaires
- **Clé API pour `tracker.gg`** (si applicable)

## **Installation**

### **Étapes**

1. **Cloner le dépôt**

    ```bash
    git clone https://github.com/your_username/KayoBot.git
    cd KayoBot
    ```

2. **Créer et activer un environnement virtuel**

    ```bash
    python -m venv venv
    ```

    - **Sur Windows**

      ```bash
      venv\Scripts\activate
      ```

    - **Sur macOS/Linux**

      ```bash
      source venv/bin/activate
      ```

3. **Installer les dépendances**

    ```bash
    pip install --upgrade pip
    pip install -r requirements.txt
    ```

4. **Configurer les variables d'environnement**

    Créez un fichier `.env` à la racine du projet et ajoutez vos configurations :

    ```env
    DISCORD_BOT_TOKEN=your_discord_bot_token_here
    AUTHORIZED_USER_ID=admin_user_id_here
    NOTIFY_USERS=user_id_to_notify_on_startup_here
    TRACKER_API_KEY=your_tracker_api_key_here
    CONFLICT_CHANNEL_ID=your_conflict_channel_id_here
    ```

    - **DISCORD_BOT_TOKEN** : Le token de votre bot Discord. Obtenez-le depuis le [portail développeur Discord](https://discord.com/developers/applications).
    - **AUTHORIZED_USER_ID** : ID de l'utilisateur administrateur par défaut.
    - **NOTIFY_USERS** : ID des utilisateurs à notifier au démarrage du bot.
    - **TRACKER_API_KEY** : Clé API pour `tracker.gg` (si utilisée).
    - **CONFLICT_CHANNEL_ID** : ID du salon Discord pour les résolutions de conflits.

5. **Créer les dossiers nécessaires**

    Assurez-vous que les dossiers `data` et `logs` existent à la racine du projet pour stocker les fichiers de configuration et les logs.

    ```bash
    mkdir data
    mkdir logs
    ```

6. **Lancer le bot**

    ```bash
    python bot.py
    ```

## **Utilisation**

### **Commandes Principales**

Utilisez le préfixe `!` pour les commandes traditionnelles et les commandes slash `/` pour les commandes intégrées.

- **Configuration des Salons**
  - `/channels get` : Affiche les salons configurés.
  - `/channels set` : Configure un salon pour une action spécifique.
  - `/channels remove` : Supprime la configuration d'un salon pour une action.

- **Économie**
  - `!daily` : Récupérer votre somme journalière.

- **Modération**
  - `/ban_perma` : Bannir un utilisateur de manière permanente.

- **Classement**
  - Diverses commandes pour gérer et afficher les classements des membres.

- **Gestion des Rôles**
  - `/refresh_rank` : Forcer la mise à jour du rôle Valorant d'un utilisateur.

- **Scrims et Tournois**
  - `/create_team` : Créer une équipe pour un scrim.
  - `/create_tournament` : Créer un nouveau tournoi.

- **Gestion des Salons Vocaux**
  - `/list_channels` : Lister tous les salons vocaux du serveur.
  - `/join <channel_name>` : Rejoindre un salon vocal spécifique.
  - `/five_stack` : Créer un salon vocal temporaire pour 5 personnes maximum.

- **Système de Signalement**
  - `/report <member>` : Signale un utilisateur.
  - `/recommend <member>` : Recommande un utilisateur.
  - `/reputation <member>` : Affiche la réputation d'un utilisateur.
  - `/remove_reports <member> <count>` : Retire des signalements d'un utilisateur (administrateurs uniquement).
  - `/remove_recommends <member> <count>` : Retire des recommandations d'un utilisateur (administrateurs uniquement).
  - `/explain_ban <reason>` : S'expliquer sur son bannissement (utilisateurs bannis uniquement).

## **Développement**

### **Structure du Projet**

```plaintext
KayoBot/
├── bot.py
├── cogs/
│   ├── configuration/
│   │   ├── channels_configuration.py
│   │   ├── role_mappings_configuration.py
│   │   └── __init__.py
│   ├── economy/
│   │   ├── economy.py
│   │   └── __init__.py
│   ├── moderation/
│   │   ├── clean.py
│   │   ├── moderation.py
│   │   └── __init__.py
│   ├── ranking/
│   │   ├── assign_rank_role.py
│   │   ├── conflict_resolution.py
│   │   ├── link_valorant.py
│   │   ├── member_join_listener.py
│   │   ├── voice_state_update_listener.py
│   │   └── __init__.py
│   ├── reputation/
│   │   ├── reputation.py
│   │   └── __init__.py
│   ├── role_management/
│   │   ├── role_assignment.py
│   │   ├── role_backup.py
│   │   ├── role_combination_management.py
│   │   └── __init__.py
│   ├── scrims/
│   │   ├── scrims.py
│   │   └── __init__.py
│   ├── tournaments/
│   │   ├── tournament_manager.py
│   │   └── __init__.py
│   └── voice_management/
│       ├── cleanup.py
│       ├── five_stack.py
│       ├── online_count_updater.py
│       └── __init__.py
├── cogs/
│   └── utilities/
│       ├── request_manager.py
│       ├── data_manager.py
│       └── __init__.py
├── data/
│   ├── config.json
│   ├── reputation.json
│   ├── scrims_data.json
│   ├── economy.json
│   ├── tournaments.json
│   ├── wins_data.json
│   └── user_data.json
├── logs/
│   └── bot.log
├── requirements.txt
└── README.md
