import json
import os
import asyncio
from typing import Dict

class DataManager:
    """Gestionnaire simple pour les données d\'économie stockées en JSON."""

    def __init__(self, file_path: str = "economy_data.json") -> None:
        self.file_path = file_path
        self.lock = asyncio.Lock()

    async def get_economy_data(self) -> Dict:
        """Lit le fichier JSON et retourne les données d'économie."""
        async with self.lock:
            if not os.path.exists(self.file_path):
                return {}
            return await asyncio.to_thread(self._read_file)

    def _read_file(self) -> Dict:
        with open(self.file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    async def save_economy_data(self, data: Dict) -> None:
        """Sauvegarde les données d'économie dans le fichier JSON."""
        async with self.lock:
            await asyncio.to_thread(self._write_file, data)

    def _write_file(self, data: Dict) -> None:
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
