# config.py

import os
from dotenv import load_dotenv

# Charger les variables d'environnement depuis le fichier .env
load_dotenv()

def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ["true", "1", "t", "yes", "y", "on"]

DATABASE = {
    'user': os.getenv('DATABASE_USER'),
    'password': os.getenv('DATABASE_PASSWORD'),
    'database': os.getenv('DATABASE_NAME'),
    'host': os.getenv('DATABASE_HOST'),
    'port': int(os.getenv('DATABASE_PORT', 5432)),
    'ssl': os.getenv('DATABASE_SSL', 'false').lower() in ['true', '1', 't']

}

# Activer le mode test
TEST_MODE = _env_bool("TEST_MODE", False)
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN_TEST" if TEST_MODE else "DISCORD_TOKEN")
TEST_GUILD_ID = os.getenv('TEST_GUILD_ID')

# Configuration des logs
LOGGING = {
    
    'bot': True,

    # CONFIGURATION
    'roles_configuration': False,
    'channels_configuration': False,

    # UTILS
    'database': False,
    'request_manager': False,

    # OTHER
    'rank_updater': False,

    # ADMIN
    'admin': True,

    # MODERATION
    'moderation' : False,
    'clean': False,
    'deban_manager' : False,

    # RANKING
    'valorant_service' : False,
    'assign_rank' : False,
    'rank_service' : False,
    'valorant_mmr' : True,
    'tracker_service' : True,


    # REPUTATION
    'reputation' : True,
    'profil' : True,

    # RULES
    'rules' : False,
    'rules_service' : False,

    # VOICE MANAGEMENT
    'five_stack' : False,
    'voice_cleaner' : False,

    # ???
    'rank_roles' : False,

    # OTHER
    'vocal.services' : False,
    'vocal.creator' : False,
    'invite_tracker' : False,
    'event_cog' : False,

    # ACCUEIL
    'accueil.services' : False,

    # SCRIMS
    'scrims.services' : False,
    'scrims' : False,

    # TWITCH
    'twitch' : True,
    'twitch.service' : True,

    # SHOP
    'shop_notif' : True,
    'valorant.shop_service' : True,

}
