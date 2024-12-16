# config.py

import os
from dotenv import load_dotenv

# Charger les variables d'environnement depuis le fichier .env
load_dotenv()

DATABASE = {
    'user': os.getenv('DATABASE_USER'),
    'password': os.getenv('DATABASE_PASSWORD'),
    'database': os.getenv('DATABASE_NAME'),
    'host': os.getenv('DATABASE_HOST'),
    'port': int(os.getenv('DATABASE_PORT', 5432)),
    'ssl': os.getenv('DATABASE_SSL', 'false').lower() in ['true', '1', 't']
}

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
TEST_GUILD_ID = os.getenv('TEST_GUILD_ID')

# Activer le mode test
TEST_MODE = False

# Configuration des logs
LOGGING = {
    'bot': True,
    'clean': False,
    'roles_configuration': False,
    'channels_configuration': False,
    'database': False,
    'request_manager': False,
    'rank_updater': False,
    # Ajoutez d'autres modules ici
}
