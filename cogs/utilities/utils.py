#cogs\utilities\utils.py
import aiofiles
import json
import logging
import os
from typing import Dict
from discord import app_commands

logger = logging.getLogger('discord.utilities.utils')

async def load_json(file_path: str) -> Dict:
    """
    Charge des données JSON depuis un fichier de manière asynchrone.
    Si le fichier n'existe pas, il est créé avec une structure vide par défaut.
    """
    if not os.path.exists(file_path):
        logger.warning(f"Fichier {file_path} non trouvé. Création d'un fichier avec des données vides.")
        # Création du fichier avec une structure vide
        dir_name = os.path.dirname(file_path)
        if not os.path.exists(dir_name):
            os.makedirs(dir_name)
        async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps({}, indent=4))
        return {}
    try:
        async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
            contents = await f.read()
            return json.loads(contents)
    except json.JSONDecodeError:
        logger.error(f"Le fichier JSON {file_path} est mal formaté. Réinitialisation avec des données vides.")
        return {}
    except Exception as e:
        logger.exception(f"Erreur lors du chargement du fichier {file_path}: {e}")
        return {}

async def save_json(file_path: str, data: Dict) -> None:
    """Sauvegarde des données JSON dans un fichier de manière asynchrone."""
    try:
        async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, indent=4))
        logger.info(f"Données sauvegardées dans {file_path}.")
    except Exception as e:
        logger.exception(f"Erreur lors de la sauvegarde du fichier {file_path}: {e}")

async def save_json_atomic(data: Dict, file_path: str) -> None:
    """Sauvegarde des données JSON dans un fichier de manière atomique."""
    try:
        dir_name = os.path.dirname(file_path)
        if not os.path.exists(dir_name):
            os.makedirs(dir_name)
        async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, indent=4))
        logger.info(f"Données sauvegardées de manière atomique dans {file_path}.")
    except Exception as e:
        logger.exception(f"Erreur lors de la sauvegarde atomique du fichier {file_path}: {e}")
