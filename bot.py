# bot.py

from __future__ import annotations

import asyncio
import logging
import os
from typing import Iterable

import discord
from discord.ext import commands

from logging_config import setup_logging
from config import DISCORD_TOKEN, TEST_GUILD_ID, LOG_LEVELS, TEST_MODE, DATABASE

from cogs.configuration.services.channel_service import ChannelConfigurationService
from cogs.configuration.services.role_service import RoleConfigurationService
from database.engine import Db, DbConfig
from database.migrate import run_migrations
from database.services.unban_requests_service import UnbanRequestsService
from integrations.http_client import HTTPClient
from integrations.henrikdev.service import HenrikDevService
from cogs.accueil.services import AccueilService
from cogs.moderation.services.clean_service import CleanService
from cogs.moderation.services.automod_service import AutomodService
from cogs.moderation.services.moderation_service import ModerationService
from cogs.file_counter.services import FileCounterService
from cogs.reputation.services import ReputationService
from cogs.role_management.services import RoleSelectionService
from cogs.rules.services import RulesService
from cogs.twitch.services import TwitchNotificationService
from cogs.voice_chat.services import TempVoiceService
from cogs.ranking.services.rank_notifications_service import RankNotificationService
from cogs.ranking.services.ranking_service import RankingService
from cogs.ranking.services.mmr_tracker_service import MmrTrackerService
from core.bootstrap import ServiceContainer, build_service_container
from integrations.twitch.service import TwitchService as TwitchApiService

# ------------------------------------------------------------
# Logging
# ------------------------------------------------------------
setup_logging(LOG_LEVELS)
logger = logging.getLogger("bot")


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def _build_postgres_dsn() -> str:
    """
    Construit une DSN à partir de config.DATABASE.
    Ex: postgresql://user:pass@host:5432/dbname?sslmode=require
    """
    user = DATABASE.get("user")
    password = DATABASE.get("password")
    host = DATABASE.get("host")
    port = DATABASE.get("port")
    dbname = DATABASE.get("database")
    ssl = DATABASE.get("ssl", False)

    missing = [k for k, v in {
        "DATABASE_USER": user,
        "DATABASE_PASSWORD": password,
        "DATABASE_HOST": host,
        "DATABASE_NAME": dbname,
    }.items() if not v]

    if missing:
        raise RuntimeError(f"Missing database config env vars: {', '.join(missing)}")

    # asyncpg accepte l’URL classique
    dsn = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
    if ssl:
        # postgresql URL standard
        dsn += "?sslmode=require"
    return dsn


COG_PATHS: list[str] = [
    "cogs.configuration.channels_configuration",
    "cogs.configuration.roles_configuration",
    "cogs.accueil.accueil",
    "cogs.accueil.stalker",
    "cogs.admin.status",
    "cogs.admin.permissions_report",
    "cogs.moderation.clean",
    "cogs.moderation.moderation",
    "cogs.moderation.automod",
    "cogs.moderation.unban_requests",
    "cogs.file_counter.file_counter",
    "cogs.reputation.reputation",
    "cogs.rules.rules",
    "cogs.role_management.game_role",
    "cogs.role_management.language_role",
    "cogs.twitch.twitch",
    "cogs.voice_chat.temp_voice",
    "cogs.ranking.assign_rank",
    "cogs.ranking.rank_notifications",
    "cogs.ranking.mmr_tracker",
]


# ------------------------------------------------------------
# Bot
# ------------------------------------------------------------
class KayoBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.all()
        intents.guilds = True
        intents.members = True
        intents.messages = True
        intents.message_content = True

        super().__init__(command_prefix="!", intents=intents)


        # Will be set in setup_hook()
        self.db: Db | None = None
        self.services: ServiceContainer | None = None
        self._http_client: HTTPClient | None = None
        self.channel_configuration_service: ChannelConfigurationService | None = None
        self.role_configuration_service: RoleConfigurationService | None = None
        self.accueil_service: AccueilService | None = None
        self.clean_service: CleanService | None = None
        self.automod_service: AutomodService | None = None
        self.moderation_service: ModerationService | None = None
        self.unban_requests_svc: UnbanRequestsService | None = None
        self.file_counter_service: FileCounterService | None = None
        self.reputation_service: ReputationService | None = None
        self.rules_service: RulesService | None = None
        self.role_selection_service: RoleSelectionService | None = None
        self.twitch_notification_service: TwitchNotificationService | None = None
        self.twitch_api_service: TwitchApiService | None = None
        self.temp_voice_service: TempVoiceService | None = None
        self.ranking_service: RankingService | None = None
        self.rank_notification_service: RankNotificationService | None = None
        self.henrik_service: HenrikDevService | None = None
        self.mmr_tracker_service: MmrTrackerService | None = None

    async def setup_hook(self) -> None:
        """
        Called once, before on_ready. Good place for:
        - DB init
        - migrations
        - loading cogs
        - syncing app commands
        """
        # 1) DB init + migrations
        dsn = _build_postgres_dsn()
        self.db = Db(DbConfig(dsn=dsn))
        await self.db.open()
        logger.info("DB pool opened.")

        await run_migrations(self.db)
        logger.info("Migrations applied.")

        # 2) Initialize services
        henrik_api_key = os.getenv("HENRIK_VALO_KEY", "")
        self.services = await build_service_container(
            self.db,
            henrik_api_key,
            twitch_client_id=os.getenv("TWITCH_CLIENT_ID", ""),
            twitch_client_secret=os.getenv("TWITCH_CLIENT_SECRET", ""),
        )
        self._http_client = self.services.http_client
        self.channel_configuration_service = self.services.channel_configuration_service
        self.role_configuration_service = self.services.role_configuration_service
        self.accueil_service = self.services.accueil_service
        self.clean_service = self.services.clean_service
        self.automod_service = self.services.automod_service
        self.moderation_service = self.services.moderation_service
        self.unban_requests_svc = self.services.unban_requests_service
        self.file_counter_service = self.services.file_counter_service
        self.reputation_service = self.services.reputation_service
        self.rules_service = self.services.rules_service
        self.role_selection_service = self.services.role_selection_service
        self.twitch_notification_service = self.services.twitch_notification_service
        self.twitch_api_service = self.services.twitch_api_service
        self.temp_voice_service = self.services.temp_voice_service
        self.ranking_service = self.services.ranking_service
        self.rank_notification_service = self.services.rank_notification_service
        self.henrik_service = self.services.henrik_service
        self.mmr_tracker_service = self.services.mmr_tracker_service
        logger.info("AccueilService initialized.")
        logger.info("CleanService initialized.")
        logger.info("AutomodService initialized.")
        logger.info("ModerationService initialized.")
        logger.info("FileCounterService initialized.")
        logger.info("ReputationService initialized.")
        logger.info("Rules + role selection services initialized.")
        logger.info("TwitchNotificationService initialized.")
        logger.info("TempVoiceService initialized.")
        logger.info("Ranking + rank notifications + MmrTracker services initialized.")

        # 3) Load extensions (cogs)
        await self._load_extensions(COG_PATHS)

        # 4) Sync slash commands
        await self._sync_app_commands()

    async def close(self) -> None:
        """
        Graceful shutdown.
        """
        try:
            await super().close()
        finally:
            if self._http_client is not None:
                await self._http_client.close()
                self._http_client = None
                logger.info("HTTP client closed.")
            if self.db is not None:
                await self.db.close()
                self.db = None
                logger.info("DB pool closed.")
            await asyncio.sleep(0.25)

    async def on_ready(self) -> None:
        logger.info("Connected as %s", self.user)

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: discord.app_commands.AppCommandError,
    ) -> None:
        logger.exception("Slash command error: %s", error)
        try:
            if interaction.response.is_done():
                await interaction.followup.send("Une erreur interne est survenue.", ephemeral=True)
            else:
                await interaction.response.send_message("Une erreur interne est survenue.", ephemeral=True)
        except Exception:
            pass

    async def _load_extensions(self, paths: Iterable[str]) -> None:
        failures: list[str] = []
        for cog_path in paths:
            try:
                await self.load_extension(cog_path)
                logger.info("Cog loaded: %s", cog_path)
            except commands.errors.ExtensionAlreadyLoaded:
                logger.warning("Cog already loaded: %s", cog_path)
            except commands.errors.ExtensionNotFound:
                logger.error("Cog not found: %s", cog_path)
                failures.append(cog_path)
            except commands.errors.NoEntryPointError:
                logger.error("No setup() in cog: %s", cog_path)
                failures.append(cog_path)
            except Exception:
                logger.exception("Failed to load cog: %s", cog_path)
                failures.append(cog_path)

        if failures:
            raise RuntimeError(f"Failed to load required cogs: {', '.join(failures)}")

    async def _sync_app_commands(self) -> None:
        """
        Sync commands globally (prod) or to test guild (dev).
        """
        # Discord can rate limit sync; keep it simple and safe.
        await asyncio.sleep(1)

        try:
            if TEST_MODE:
                if not TEST_GUILD_ID:
                    logger.error("TEST_MODE=True but TEST_GUILD_ID is missing; skipping sync.")
                    return
                guild_id = int(TEST_GUILD_ID)
                guild = discord.Object(id=guild_id)

                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                logger.info("Synced to test guild %s: %s commands", guild_id, len(synced))
            else:
                synced = await self.tree.sync()
                logger.info("Synced globally: %s commands", len(synced))
        except Exception:
            logger.exception("Command sync failed")


bot = KayoBot()


async def main() -> None:
    if not DISCORD_TOKEN:
        logger.error("DISCORD_TOKEN missing (TEST_MODE=%s).", TEST_MODE)
        return

    async with bot:
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
