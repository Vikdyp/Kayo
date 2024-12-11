import json
import aiofiles
import os
import logging
from typing import Dict, Any

logger = logging.getLogger("discord.utilities.data_manager")


class DataManager:
    def __init__(self):
        self.config_file = 'data/config.json'
        self.reputation_file = 'data/reputation.json'
        self.scrims_file = 'data/scrims_data.json'
        self.economy_file = 'data/economy.json'
        self.tournaments_file = 'data/tournaments.json'
        self.wins_file = 'data/wins_data.json'
        self.user_data_file = 'data/user_data.json'
        self.role_backup_file = 'data/role_backup.json'
        self.teams_file = "data/teams_data.json"
        self.moderation_file = "data/moderation_data.json"
        self.leaderboard_file = "data/leaderboard_data.json"

    async def load_json(self, file_path: str) -> Dict:
        """Charge un fichier JSON et renvoie son contenu."""
        if not os.path.exists(file_path):
            # Crée un fichier vide s'il n'existe pas
            dir_name = os.path.dirname(file_path)
            if dir_name and not os.path.exists(dir_name):
                os.makedirs(dir_name)
            async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps({}, indent=4))
            return {}

        try:
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                data = json.loads(content)
                logger.debug(f"Fichier chargé avec succès : {file_path}")
                return data
        except json.JSONDecodeError:
            logger.error(f"Le fichier {file_path} est mal formaté. Réinitialisation.")
            return {}
        except Exception as e:
            logger.error(f"Erreur lors du chargement du fichier {file_path}: {e}")
            return {}

    async def save_json(self, file_path: str, data: Dict) -> None:
        """Sauvegarde des données dans un fichier JSON."""
        dir_name = os.path.dirname(file_path)
        if dir_name and not os.path.exists(dir_name):
            os.makedirs(dir_name)
        try:
            async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(data, indent=4))
            logger.debug(f"Données sauvegardées dans {file_path}")
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde du fichier {file_path}: {e}")

    async def get_config(self) -> Dict:
        """Charge la configuration et valide sa structure."""
        config = await self.load_json(self.config_file)
        if not self.validate_config(config):
            logger.error("Configuration invalide. Utilisation d'une configuration vide.")
            return {}
        return config

    async def save_config(self, config_data: Dict) -> None:
        """Sauvegarde la configuration."""
        if not self.validate_config(config_data):
            logger.error("Tentative de sauvegarde d'une configuration invalide.")
            return
        await self.save_json(self.config_file, config_data)

    def validate_config(self, config: Dict) -> bool:
        """Valide la structure de la configuration."""
        if not isinstance(config, dict):
            logger.error("La configuration doit être un dictionnaire.")
            return False

        # Vérification des clés principales
        required_keys = ["channels", "roles"]
        for key in required_keys:
            if key not in config:
                logger.error(f"Clé manquante dans la configuration : {key}")
                return False

        # Validation des channels
        if not isinstance(config.get("channels"), dict):
            logger.error("La section 'channels' doit être un dictionnaire.")
            return False

        # Validation des roles
        if not isinstance(config.get("roles"), dict):
            logger.error("La section 'roles' doit être un dictionnaire.")
            return False

        # Exemple de validation supplémentaire pour un channel spécifique
        channels = config["channels"]
        if "demande-deban" not in channels or not isinstance(channels["demande-deban"], int):
            logger.error("La clé 'demande-deban' est manquante ou invalide dans 'channels'.")
            return False

        logger.debug("Validation de la configuration réussie.")
        return True

    # Configuration
    async def get_config(self) -> Dict:
        return await self.load_json(self.config_file)

    async def save_config(self, config_data: Dict) -> None:
        await self.save_json(self.config_file, config_data)

    # Réputation
    async def get_reputation_data(self) -> Dict:
        return await self.load_json(self.reputation_file)
    
    async def save_reputation_data(self, data: Dict) -> None:
        await self.save_json(self.reputation_file, data)

    # Scrims
    async def get_scrims_data(self) -> Dict:
        return await self.load_json(self.scrims_file)

    async def save_scrims_data(self, data: Dict) -> None:
        await self.save_json(self.scrims_file, data)

    # Économie
    async def get_economy_data(self) -> Dict:
        return await self.load_json(self.economy_file)

    async def save_economy_data(self, data: Dict) -> None:
        await self.save_json(self.economy_file, data)

    # Tournois
    async def get_tournaments_data(self) -> Dict:
        return await self.load_json(self.tournaments_file)

    async def save_tournaments_data(self, data: Dict) -> None:
        await self.save_json(self.tournaments_file, data)

    # Utilisateurs
    async def get_user_data(self) -> Dict:
        return await self.load_json(self.user_data_file)

    async def save_user_data(self, data: Dict) -> None:
        await self.save_json(self.user_data_file, data)

    # Victoires
    async def get_wins_data(self) -> Dict:
        return await self.load_json(self.wins_file)

    async def save_wins_data(self, data: Dict) -> None:
        await self.save_json(self.wins_file, data)

    # Sauvegarde des rôles
    async def get_role_backup(self) -> Dict:
        """Charge le backup des rôles depuis le fichier role_backup.json."""
        return await self.load_json(self.role_backup_file)

    async def save_role_backup(self, data: Dict) -> None:
        """Sauvegarde le backup des rôles dans le fichier role_backup.json."""
        await self.save_json(self.role_backup_file, data)

    # Équipes
    async def get_teams_data(self) -> Dict:
        """Charge les données des équipes depuis le fichier JSON."""
        return await self.load_json(self.teams_file)

    # Modération
    async def get_moderation_data(self) -> Dict:
        moderation_data = await self.load_json(self.moderation_file)
        if "bans" not in moderation_data:
            moderation_data["bans"] = {}
        return moderation_data

    async def save_moderation_data(self, data: Dict) -> None:
        """Sauvegarde les données de modération dans le fichier JSON."""
        await self.save_json(self.moderation_file, data)

    # Tableau des scores
    async def get_leaderboard_data(self) -> Dict:
        """Charge les données du tableau des scores depuis le fichier JSON."""
        return await self.load_json(self.leaderboard_file)

    async def save_leaderboard_data(self, data: Dict) -> None:
        """Sauvegarde les données du tableau des scores dans le fichier JSON."""
        await self.save_json(self.leaderboard_file, data)


# Exemple d'utilisation
if __name__ == "__main__":
    import asyncio

    async def main():
        data_manager = DataManager()
        config = await data_manager.get_config()
        print(config)

    asyncio.run(main())
