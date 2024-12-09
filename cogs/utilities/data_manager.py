#cogs\utilities\data_manager.py
import json
import aiofiles
import os
import logging

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
