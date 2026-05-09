from __future__ import annotations

import logging

import discord
from discord.ext import commands, tasks

from cogs.ranking.services.online_count_service import (
    ChannelEditRateLimiter,
    RankOnlineCountConfig,
    RankOnlineCountService,
)

logger = logging.getLogger(__name__)


class RankOnlineCountCog(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
        service: RankOnlineCountService,
        *,
        rate_limiter: ChannelEditRateLimiter | None = None,
    ) -> None:
        self.bot = bot
        self._service = service
        self._rate_limiter = rate_limiter or ChannelEditRateLimiter()
        self.refresh_rank_counts.start()
        logger.info("RankOnlineCountCog initialized.")

    def cog_unload(self) -> None:
        if self.refresh_rank_counts.is_running():
            self.refresh_rank_counts.cancel()
        self._rate_limiter.clear()

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member) -> None:
        if not self._service.presence_crossed_online_boundary(
            before.status,
            after.status,
            discord.Status.offline,
        ):
            return

        config = await self._service.get_config(after.guild.id)
        changed_ranks = self._service.rank_names_for_role_ids(
            (role.id for role in after.roles),
            config,
        )
        if not changed_ranks:
            return

        await self.refresh_guild(after.guild, config=config, only_ranks=changed_ranks)

    @tasks.loop(minutes=10)
    async def refresh_rank_counts(self) -> None:
        for guild in self.bot.guilds:
            try:
                await self.refresh_guild(guild)
            except Exception:
                logger.exception("Rank online count refresh failed for guild %s.", guild.id)

    @refresh_rank_counts.before_loop
    async def before_refresh_rank_counts(self) -> None:
        await self.bot.wait_until_ready()

    async def refresh_guild(
        self,
        guild: discord.Guild,
        *,
        config: RankOnlineCountConfig | None = None,
        only_ranks: frozenset[str] | None = None,
    ) -> None:
        config = config or await self._service.get_config(guild.id)
        ranks_to_refresh = config.configured_ranks if only_ranks is None else config.configured_ranks & only_ranks
        if not ranks_to_refresh:
            return

        for rank in sorted(ranks_to_refresh):
            role = guild.get_role(config.rank_roles[rank])
            channel = guild.get_channel(config.rank_channels[rank])
            if role is None or channel is None:
                continue

            online_count = sum(1 for member in role.members if member.status != discord.Status.offline)
            await self._rename_channel_if_needed(channel, self._service.channel_name(rank, online_count))

    async def _rename_channel_if_needed(self, channel, new_name: str) -> None:
        if getattr(channel, "name", None) == new_name:
            return

        if not self._rate_limiter.allow(channel.id):
            logger.warning("Rank online count rename skipped for channel %s: rate limit reached.", channel.id)
            return

        try:
            await channel.edit(name=new_name, reason="Mise a jour compteur rangs en ligne.")
            logger.info("Rank online count channel %s renamed to %s.", channel.id, new_name)
        except discord.Forbidden:
            logger.error("Missing permission to rename rank online count channel %s.", channel.id)
        except discord.HTTPException as exc:
            logger.error("HTTP error while renaming rank online count channel %s: %s", channel.id, exc)


async def setup(bot: commands.Bot) -> None:
    role_service = getattr(bot, "role_configuration_service", None)
    channel_service = getattr(bot, "channel_configuration_service", None)
    if role_service is None or channel_service is None:
        logger.error("RankOnlineCountCog not loaded: configuration services are missing.")
        return

    service = RankOnlineCountService(role_service, channel_service)
    await bot.add_cog(RankOnlineCountCog(bot, service))
    logger.info("RankOnlineCountCog loaded.")
