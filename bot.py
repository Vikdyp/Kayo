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
from database.services.guild_roles_service import RoleConfigurationService
from database.services.message_deletions_service import MessageDeletionsService
from database.services.automod_config_service import AutomodConfigService
from database.services.moderation_service import ModerationDbService
from database.services.unban_requests_service import UnbanRequestsService
from database.services.guild_members_service import GuildMembersService
from database.services.valorant_info_service import ValorantInfoService
from cogs.accueil.services import AccueilService
from cogs.moderation.services.clean_service import CleanService
from cogs.moderation.services.automod_service import AutomodService
from cogs.moderation.services.moderation_service import ModerationService

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
    "cogs.moderation.clean",
    "cogs.moderation.moderation",
    "cogs.moderation.automod",
    "cogs.moderation.unban_requests",
    "cogs.rules.rules",
    "cogs.role_management.auto_role",
    "cogs.update.rank_up",
    "cogs.update.online_count_updater",
    "cogs.voice_chat.vocal_creator",
    "cogs.role_management.game_role",
    "cogs.role_management.language_role",
    "cogs.role_management.role_combination",
    "cogs.troll.quoicoubeh",
    "cogs.twitch.twitch_notifier",
    "cogs.file_counter.file_counter",
    "cogs.shop.shop_notifier",
    "cogs.ranking.assign_rank",
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
        self.accueil_service: AccueilService | None = None
        self.clean_service: CleanService | None = None
        self.automod_service: AutomodService | None = None
        self.moderation_service: ModerationService | None = None
        self.unban_requests_svc: UnbanRequestsService | None = None

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

        # 2) Initialize DB services
        member_stats_svc = MemberStatsService(self.db)
        persistent_msg_svc = PersistentMessagesService(self.db)
        channel_config_svc = ChannelConfigurationService(self.db)
        role_config_svc = RoleConfigurationService(self.db)
        message_deletions_svc = MessageDeletionsService(self.db)
        automod_config_svc = AutomodConfigService(self.db)
        moderation_db_svc = ModerationDbService(self.db)
        self.unban_requests_svc = UnbanRequestsService(self.db)
        guild_members_svc = GuildMembersService(self.db)

        valorant_info_svc = ValorantInfoService(self.db)

        # Expose DB services needed by cogs (for injection in setup())
        self.channel_config_svc = channel_config_svc
        self.role_config_svc = role_config_svc
        self.persistent_msg_svc = persistent_msg_svc
        self.guild_members_svc = guild_members_svc
        self.valorant_info_svc = valorant_info_svc

        # 3) Initialize business services
        self.accueil_service = AccueilService(
            member_stats_svc, persistent_msg_svc, channel_config_svc
        )
        logger.info("AccueilService initialized.")

        self.clean_service = CleanService(message_deletions_svc)
        logger.info("CleanService initialized.")

        self.automod_service = AutomodService(automod_config_svc, channel_config_svc)
        logger.info("AutomodService initialized.")

        self.moderation_service = ModerationService(
            moderation_db_svc,
            persistent_msg_svc,
            role_config_svc,
            channel_config_svc,
        )
        logger.info("ModerationService initialized.")

        # 4) Load extensions (cogs)
        await self._load_extensions(COG_PATHS)

        # 5) Sync slash commands
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