# cogs\utilities\data_manager.py
import json
import aiofiles
import os
import logging
from discord import app_commands

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
        self.role_backup_file = 'data/role_backup.json'  # MODIF: Ajout du chemin vers le fichier role_backup
        self.teams_file = "data/teams_data.json"
        self.moderation_file = "data/moderation_data.json"

    async def load_json(self, file_path: str):
        if not os.path.exists(file_path):
            dir_name = os.path.dirname(file_path)
            if dir_name and not os.path.exists(dir_name):
                os.makedirs(dir_name)
            async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps({}, indent=4))
            return {}
        async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
            content = await f.read()
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                logger.error(f"Le fichier {file_path} est mal formaté. Réinitialisation.")
                return {}

    async def save_json(self, file_path: str, data: dict):
        dir_name = os.path.dirname(file_path)
        if dir_name and not os.path.exists(dir_name):
            os.makedirs(dir_name)
        async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, indent=4))

    async def get_config(self):
        return await self.load_json(self.config_file)

    async def save_config(self, config_data: dict):
        await self.save_json(self.config_file, config_data)

    async def get_reputation_data(self):
        return await self.load_json(self.reputation_file)
    
    async def save_reputation_data(self, data: dict):
        await self.save_json(self.reputation_file, data)

    async def get_scrims_data(self):
        return await self.load_json(self.scrims_file)

    async def save_scrims_data(self, data: dict):
        await self.save_json(self.scrims_file, data)

    async def get_economy_data(self):
        return await self.load_json(self.economy_file)

    async def save_economy_data(self, data: dict):
        await self.save_json(self.economy_file, data)

    async def get_tournaments_data(self):
        return await self.load_json(self.tournaments_file)

    async def save_tournaments_data(self, data: dict):
        await self.save_json(self.tournaments_file, data)

    async def get_user_data(self):
        return await self.load_json(self.user_data_file)

    async def save_user_data(self, data: dict):
        await self.save_json(self.user_data_file, data)

    async def get_wins_data(self):
        return await self.load_json(self.wins_file)

    async def save_wins_data(self, data: dict):
        await self.save_json(self.wins_file, data)

    # MODIF: Ajout des méthodes pour role_backup
    async def get_role_backup(self):
        """Charge le backup des rôles depuis le fichier role_backup.json."""
        return await self.load_json(self.role_backup_file)

    async def save_role_backup(self, data: dict):
        """Sauvegarde le backup des rôles dans le fichier role_backup.json."""
        await self.save_json(self.role_backup_file, data)

    async def get_teams_data(self):
        """Charge les données des équipes depuis le fichier JSON."""
        return await self.load_json(self.teams_file)  # Assurez-vous que self.teams_file est défini.

    async def get_moderation_data(self):
        moderation_data = await self.load_json(self.moderation_file)
        if "bans" not in moderation_data:
            moderation_data["bans"] = {}
        return moderation_data

    
    async def get_leaderboard_data(self):
        """Charge les données du tableau des scores depuis le fichier JSON."""
        leaderboard_file = "data/leaderboard_data.json"  # Assurez-vous que ce chemin est correct.
        return await self.load_json(leaderboard_file)

    async def save_leaderboard_data(self, data: dict):
        """Sauvegarde les données du tableau des scores dans le fichier JSON."""
        leaderboard_file = "data/leaderboard_data.json"
        await self.save_json(leaderboard_file, data)
