# bot.py

import asyncio
import logging
from typing import Iterable

import discord
from discord.ext import commands

from logging_config import setup_logging
from config import DISCORD_TOKEN, TEST_GUILD_ID, LOG_LEVELS, TEST_MODE, DATABASE

from database.engine import Db, DbConfig
from database.migrate import run_migrations
from database.services.member_stats_service import MemberStatsService
from database.services.persistent_messages_service import PersistentMessagesService
from database.services.guild_channels_service import ChannelConfigurationService
from cogs.accueil.services import AccueilService

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
        self.accueil_service: AccueilService | None = None

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
        member_stats_svc = MemberStatsService(self.db)
        persistent_msg_svc = PersistentMessagesService(self.db)
        channel_config_svc = ChannelConfigurationService(self.db)
        self.accueil_service = AccueilService(
            member_stats_svc, persistent_msg_svc, channel_config_svc
        )
        logger.info("AccueilService initialized.")

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
            if self.db is not None:
                await self.db.close()
                logger.info("DB pool closed.")

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
        for cog_path in paths:
            try:
                await self.load_extension(cog_path)
                logger.info("Cog loaded: %s", cog_path)
            except commands.errors.ExtensionAlreadyLoaded:
                logger.warning("Cog already loaded: %s", cog_path)
            except commands.errors.ExtensionNotFound:
                logger.error("Cog not found: %s", cog_path)
            except commands.errors.NoEntryPointError:
                logger.error("No setup() in cog: %s", cog_path)
            except Exception:
                logger.exception("Failed to load cog: %s", cog_path)

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