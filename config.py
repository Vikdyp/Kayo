# config.py
import os
import logging
from dotenv import load_dotenv

load_dotenv()

def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"true", "1", "t", "yes", "y", "on"}

TEST_MODE = _env_bool("TEST_MODE", False)

DATABASE = {
    "user": os.getenv("DATABASE_USER"),
    "password": os.getenv("DATABASE_PASSWORD"),
    "database": os.getenv("DATABASE_TEST_NAME" if TEST_MODE else "DATABASE_NAME"),
    "host": os.getenv("DATABASE_HOST"),
    "port": int(os.getenv("DATABASE_PORT", 5432)),
    "ssl": os.getenv("DATABASE_SSL", "false").lower() in {"true", "1", "t"},
}

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN_TEST" if TEST_MODE else "DISCORD_TOKEN")
TEST_GUILD_ID = os.getenv("TEST_GUILD_ID")

# Logging: clés = noms de loggers (idéalement __name__)
LOG_LEVELS = {
    # Ton entrypoint
    "bot": logging.INFO,

    # Discord.py est verbeux
    "discord": logging.INFO,
    "discord.http": logging.INFO,

    # Cogs (règle globale)
    "cogs": logging.INFO,

    # Tu peux affiner un sous-module si besoin
    "cogs.moderation": logging.INFO,
    "cogs.twitch": logging.INFO,

    # Intégrations / services
    "integrations": logging.INFO,
    "integrations.henrikdev": logging.DEBUG,

    # Utils
    "utils": logging.INFO,
}
