# KayoBot

KayoBot est un bot Discord développé en Python utilisant la bibliothèque `discord.py`. Il offre une variété de fonctionnalités pour gérer les salons, les rôles, les scrims, les rapports et plus encore.

## **Fonctionnalités**

- **Gestion des Messages** : Nettoyage des messages dans les salons.
- **Heartbeat** : Envoi régulier de messages pour maintenir l'activité du bot.
- **Gestion des Rangs** : Attribution de rôles basés sur les rangs des utilisateurs dans Valorant.
- **Système de Signalement** : Signalement et recommandation des utilisateurs avec gestion des rôles associés.
- **Gestion des Rôles** : Attribution automatique de rôles basés sur les combinaisons de rôles existants.
- **Gestion des Scrims** : Inscription, création de salons vocaux, suivi des résultats.
- **Gestion des Salons Vocaux** : Listage, rejoindre et création de salons vocaux temporaires.

## **Installation**

### **Prérequis**

- Python 3.8 ou supérieur
- Un bot Discord avec les permissions nécessaires
- Clé API pour `tracker.gg`

### **Étapes**

1. **Cloner le dépôt :**

    ```bash
    git clone https://github.com/your_username/KayoBot.git
    cd KayoBot
    ```

2. **Créer et activer un environnement virtuel :**

    ```bash
    python -m venv venv
    # Sur Windows
    venv\Scripts\activate
    # Sur macOS/Linux
    source venv/bin/activate
    ```

3. **Installer les dépendances :**

    ```bash
    pip install -r requirements.txt
    ```

4. **Configurer les variables d'environnement :**

    Créez un fichier `.env` à la racine du projet et ajoutez vos configurations :

    ```
    DISCORD_BOT_TOKEN=your_discord_bot_token_here
    AUTHORIZED_USER_ID=812367371570118756
    NOTIFY_USERS=812367371570118756,695321590908453027
    CLEAN_ROLE_ID=1236375048252817418
    ADMIN_ROLE_ID=1236375048252817418
    TRACKER_API_KEY=your_tracker_api_key_here
    CONFLICT_CHANNEL_ID=your_conflict_channel_id_here
    ```

5. **Lancer le bot :**

    ```bash
    python main.py
    ```

## **Utilisation**

### **Commandes Principales**

- `/clean_all` : Supprime tous les messages dans le salon actuel.
- `/clean_number <count>` : Supprime un nombre spécifié de messages dans le salon actuel.
- `/sync_all` : Synchronise toutes les commandes (réservé aux utilisateurs autorisés).
- `/link_valorant <tracker_url>` : Lie un compte Valorant à votre compte Discord.
- `/report <member>` : Signale un utilisateur.
- `/recommend <member>` : Recommande un utilisateur.
- `/reputation <member>` : Affiche la réputation d'un utilisateur.
- `/remove_reports <member> <count>` : Retire des signalements d'un utilisateur (administrateurs uniquement).
- `/remove_recommends <member> <count>` : Retire des recommandations d'un utilisateur (administrateurs uniquement).
- `/explain_ban <reason>` : S'expliquer sur son bannissement (utilisateurs bannis uniquement).
- `/inscription_scrims` : S'inscrire pour un scrim selon votre rang.
- `/retirer_inscription` : Retirer votre inscription des scrims.
- `/list_channels` : Lister tous les salons vocaux du serveur.
- `/join <channel_name>` : Rejoindre un salon vocal spécifique.
- `/five_stack` : Créer un salon vocal temporaire pour 5 personnes maximum.

## **Contribution**

Les contributions sont les bienvenues ! Veuillez ouvrir une issue ou soumettre une pull request pour toute amélioration ou bug.

## **Licence**

[MIT](LICENSE)
