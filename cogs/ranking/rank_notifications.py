from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import discord
from discord.ext import commands

from cogs.ranking.presenters.rank_notifications import build_rank_change_message
from cogs.ranking.services.rank_notifications_service import (
    RankNotificationConfig,
    RankNotificationService,
)

logger = logging.getLogger(__name__)

ROLE_REPLACEMENT_WINDOW_SECONDS = 2.0


@dataclass(slots=True)
class PendingRankRemoval:
    removed: frozenset[str]
    created_at: float


class RankNotificationsCog(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
        rank_notification_service: RankNotificationService,
        *,
        replacement_window_seconds: float = ROLE_REPLACEMENT_WINDOW_SECONDS,
    ) -> None:
        self.bot = bot
        self._service = rank_notification_service
        self._replacement_window_seconds = replacement_window_seconds
        self._pending_removals: dict[tuple[int, int], PendingRankRemoval] = {}
        self._cleanup_tasks: dict[tuple[int, int], asyncio.Task] = {}
        logger.info("RankNotificationsCog initialized.")

    def cog_unload(self) -> None:
        for task in self._cleanup_tasks.values():
            task.cancel()
        self._cleanup_tasks.clear()
        self._pending_removals.clear()

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        config = await self._service.get_config(after.guild.id)
        if not config.is_complete:
            return

        delta = self._service.analyze_role_delta(
            before_role_ids=(role.id for role in before.roles),
            after_role_ids=(role.id for role in after.roles),
            config=config,
        )
        key = (after.guild.id, after.id)

        if delta.removed:
            self._store_pending_removal(key, delta.removed)

        if delta.added:
            pending = self._pending_removals.get(key)
            if pending is None or len(pending.removed) != 1 or len(delta.added) != 1:
                return

            old_rank = next(iter(pending.removed))
            new_rank = next(iter(delta.added))
            self._clear_pending_removal(key)
            await self._send_rank_change_message(after, old_rank, new_rank, config)

    def _store_pending_removal(self, key: tuple[int, int], removed: frozenset[str]) -> None:
        self._clear_pending_removal(key)
        self._pending_removals[key] = PendingRankRemoval(removed=removed, created_at=time.time())
        task = asyncio.create_task(self._expire_pending_removal(key))
        self._cleanup_tasks[key] = task
        task.add_done_callback(lambda done_task, item_key=key: self._cleanup_tasks.pop(item_key, None))

    def _clear_pending_removal(self, key: tuple[int, int]) -> None:
        self._pending_removals.pop(key, None)
        task = self._cleanup_tasks.pop(key, None)
        if task is not None:
            task.cancel()

    async def _expire_pending_removal(self, key: tuple[int, int]) -> None:
        try:
            await asyncio.sleep(self._replacement_window_seconds)
            pending = self._pending_removals.get(key)
            if pending is None:
                return
            if time.time() - pending.created_at >= self._replacement_window_seconds:
                self._pending_removals.pop(key, None)
        except asyncio.CancelledError:
            raise

    async def _send_rank_change_message(
        self,
        member: discord.Member,
        old_rank: str,
        new_rank: str,
        config: RankNotificationConfig,
    ) -> None:
        if config.log_channel_id is None:
            return

        channel = member.guild.get_channel(config.log_channel_id)
        if not isinstance(channel, discord.TextChannel):
            logger.warning("Rank notification channel %s not found.", config.log_channel_id)
            return

        top_percentile = self._service.calculate_top_percentile(
            guild_member_role_ids=([role.id for role in guild_member.roles] for guild_member in member.guild.members),
            new_rank=new_rank,
            config=config,
        )
        emoji_obj = discord.utils.get(member.guild.emojis, name=new_rank)
        message = build_rank_change_message(
            member_mention=member.mention,
            old_rank=old_rank,
            new_rank=new_rank,
            top_percentile=top_percentile,
            emoji=str(emoji_obj) if emoji_obj else "",
        )
        await channel.send(message)


async def setup(bot: commands.Bot) -> None:
    rank_notification_service = getattr(bot, "rank_notification_service", None)
    if rank_notification_service is None:
        logger.error("rank_notification_service is not initialized. RankNotificationsCog will not be loaded.")
        return
    await bot.add_cog(RankNotificationsCog(bot, rank_notification_service))
    logger.info("RankNotificationsCog loaded.")
