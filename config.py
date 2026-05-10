from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Mapping

from dotenv import load_dotenv

from database.dsn import build_database_dsn_from_env, env_bool


load_dotenv()


class ConfigValidationError(RuntimeError):
    """Raised when the runtime environment cannot start safely."""


@dataclass(frozen=True, slots=True)
class DatabaseSettings:
    direct_dsn: str | None
    user: str | None
    password: str | None
    name: str | None
    test_name: str | None
    host: str | None
    port: int
    ssl: bool

    def selected_database_env_name(self, *, test_mode: bool) -> str:
        return "DATABASE_TEST_NAME" if test_mode else "DATABASE_NAME"

    def selected_database_name(self, *, test_mode: bool) -> str | None:
        return self.test_name if test_mode else self.name

    def missing_required_env_names(self, *, test_mode: bool) -> tuple[str, ...]:
        if self.direct_dsn:
            return ()

        selected_database_env = self.selected_database_env_name(test_mode=test_mode)
        selected_database = self.selected_database_name(test_mode=test_mode)
        required = {
            "DATABASE_USER": self.user,
            "DATABASE_PASSWORD": self.password,
            "DATABASE_HOST": self.host,
            selected_database_env: selected_database,
        }
        return tuple(name for name, value in required.items() if not value)

    def dsn(self, *, test_mode: bool) -> str:
        values = {
            "TEST_MODE": "true" if test_mode else "false",
            "DATABASE_PORT": str(self.port),
            "DATABASE_SSL": "true" if self.ssl else "false",
        }
        optional_values = {
            "DATABASE_URL": self.direct_dsn,
            "DATABASE_USER": self.user,
            "DATABASE_PASSWORD": self.password,
            "DATABASE_NAME": self.name,
            "DATABASE_TEST_NAME": self.test_name,
            "DATABASE_HOST": self.host,
        }
        values.update({key: value for key, value in optional_values.items() if value})
        return build_database_dsn_from_env(values)

    def as_legacy_dict(self, *, test_mode: bool) -> dict[str, object]:
        return {
            "user": self.user,
            "password": self.password,
            "database": self.selected_database_name(test_mode=test_mode),
            "host": self.host,
            "port": self.port,
            "ssl": self.ssl,
        }


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    test_mode: bool
    discord_token: str | None
    test_guild_id: str | None
    database: DatabaseSettings
    henrik_valo_key: str
    twitch_client_id: str
    twitch_client_secret: str

    def missing_required_env_names(self) -> tuple[str, ...]:
        token_env = "DISCORD_TOKEN_TEST" if self.test_mode else "DISCORD_TOKEN"
        missing = []
        if not self.discord_token:
            missing.append(token_env)
        if self.test_mode and not self.test_guild_id:
            missing.append("TEST_GUILD_ID")
        missing.extend(self.database.missing_required_env_names(test_mode=self.test_mode))
        return tuple(missing)

    def operational_warnings(self) -> tuple[str, ...]:
        warnings = []
        if not self.henrik_valo_key:
            warnings.append("HENRIK_VALO_KEY missing: Valorant shop, ranking and MMR API features are limited.")
        if bool(self.twitch_client_id) != bool(self.twitch_client_secret):
            warnings.append("Twitch credentials are incomplete: set both TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET.")
        elif not self.twitch_client_id and not self.twitch_client_secret:
            warnings.append("Twitch credentials missing: Twitch live notifications are disabled.")
        return tuple(warnings)

    def database_dsn(self) -> str:
        return self.database.dsn(test_mode=self.test_mode)


def _env_int(values: Mapping[str, str], name: str, default: int) -> int:
    raw_value = values.get(name)
    if raw_value is None or raw_value == "":
        return default
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ConfigValidationError(f"{name} must be an integer, got {raw_value!r}.") from exc


def load_runtime_settings(env: Mapping[str, str] | None = None) -> RuntimeSettings:
    values = env or os.environ
    test_mode = env_bool(values, "TEST_MODE", False)
    database = DatabaseSettings(
        direct_dsn=values.get("DATABASE_URL") or values.get("POSTGRES_DSN"),
        user=values.get("DATABASE_USER"),
        password=values.get("DATABASE_PASSWORD"),
        name=values.get("DATABASE_NAME"),
        test_name=values.get("DATABASE_TEST_NAME"),
        host=values.get("DATABASE_HOST"),
        port=_env_int(values, "DATABASE_PORT", 5432),
        ssl=env_bool(values, "DATABASE_SSL", False),
    )
    return RuntimeSettings(
        test_mode=test_mode,
        discord_token=values.get("DISCORD_TOKEN_TEST" if test_mode else "DISCORD_TOKEN"),
        test_guild_id=values.get("TEST_GUILD_ID"),
        database=database,
        henrik_valo_key=values.get("HENRIK_VALO_KEY", ""),
        twitch_client_id=values.get("TWITCH_CLIENT_ID", ""),
        twitch_client_secret=values.get("TWITCH_CLIENT_SECRET", ""),
    )


def validate_runtime_config(settings: RuntimeSettings) -> None:
    missing = settings.missing_required_env_names()
    if missing:
        raise ConfigValidationError(f"Missing required environment variables: {', '.join(missing)}")


SETTINGS = load_runtime_settings()

TEST_MODE = SETTINGS.test_mode
DATABASE_DSN = SETTINGS.database.direct_dsn
DATABASE = SETTINGS.database.as_legacy_dict(test_mode=TEST_MODE)
DISCORD_TOKEN = SETTINGS.discord_token
TEST_GUILD_ID = SETTINGS.test_guild_id


LOG_LEVELS = {
    "bot": logging.INFO,
    "discord": logging.INFO,
    "discord.http": logging.INFO,
    "cogs": logging.INFO,
    "cogs.moderation": logging.INFO,
    "cogs.twitch": logging.INFO,
    "integrations": logging.INFO,
    "integrations.henrikdev": logging.DEBUG,
    "utils": logging.INFO,
}
