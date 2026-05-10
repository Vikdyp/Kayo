from __future__ import annotations

import asyncio
import logging
from typing import Optional

import discord
from discord.ext import commands, tasks

from cogs.voice_chat.services import TempVoiceConfig, TempVoiceService

logger = logging.getLogger(__name__)

IDLE_TIMEOUT_SECONDS = 5 * 60


class TempVoiceCog(commands.Cog):
    """Create temporary voice channels from a configured lobby channel."""

    def __init__(
        self,
        bot: commands.Bot,
        temp_voice_service: TempVoiceService,
        *,
        idle_timeout_seconds: int = IDLE_TIMEOUT_SECONDS,
    ) -> None:
        self.bot = bot
        self._service = temp_voice_service
        self._idle_timeout_seconds = idle_timeout_seconds
        self._deletion_tasks: dict[int, asyncio.Task] = {}
        self.voice_check_loop.start()
        logger.info("TempVoiceCog initialized.")

    def cog_unload(self) -> None:
        self.voice_check_loop.cancel()
        for task in self._deletion_tasks.values():
            task.cancel()
        self._deletion_tasks.clear()

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        config = await self._service.get_config(member.guild.id)
        if not config.is_complete:
            return

        after_channel_id = after.channel.id if after.channel else None
        if self._service.is_lobby_join(after_channel_id=after_channel_id, config=config):
            await self._create_temp_channel_for_member(member, config)

        if self._service.should_cancel_deletion(after.channel, config=config):
            self._cancel_deletion(after.channel.id)

        if self._service.should_schedule_deletion(before.channel, config=config):
            self._schedule_deletion(before.channel)
        elif self._service.should_cancel_deletion(before.channel, config=config):
            self._cancel_deletion(before.channel.id)

    async def _create_temp_channel_for_member(
        self,
        member: discord.Member,
        config: TempVoiceConfig,
    ) -> None:
        category = member.guild.get_channel(config.category_id)
        if not isinstance(category, discord.CategoryChannel):
            logger.warning("Temp voice category %s not found in guild %s.", config.category_id, member.guild.id)
            return

        channel_name = self._service.build_temp_channel_name(member.display_name)
        await self._delete_empty_duplicate_channels(member.guild, config, channel_name)

        try:
            new_channel = await member.guild.create_voice_channel(
                name=channel_name,
                category=category,
                reason="Creation de salon vocal temporaire.",
            )
            await member.move_to(new_channel, reason="Deplacement vers salon vocal temporaire.")
            self._schedule_deletion(new_channel)
        except discord.Forbidden:
            logger.warning("Missing permissions to create or move temp voice channel in guild %s.", member.guild.id)
        except discord.HTTPException as exc:
            logger.warning("HTTP error while creating temp voice channel in guild %s: %s", member.guild.id, exc)

    async def _delete_empty_duplicate_channels(
        self,
        guild: discord.Guild,
        config: TempVoiceConfig,
        channel_name: str,
    ) -> None:
        for channel in list(guild.voice_channels):
            if (
                channel.name == channel_name
                and self._service.should_schedule_deletion(channel, config=config)
            ):
                try:
                    await channel.delete(reason="Nettoyage ancien salon vocal temporaire vide.")
                    self._cancel_deletion(channel.id)
                except discord.NotFound:
                    self._cancel_deletion(channel.id)
                except discord.Forbidden:
                    logger.warning("Missing permissions to delete duplicate temp voice channel %s.", channel.id)
                except discord.HTTPException as exc:
                    logger.warning("HTTP error while deleting duplicate temp voice channel %s: %s", channel.id, exc)

    def _schedule_deletion(self, channel: Optional[discord.VoiceChannel]) -> None:
        if channel is None or channel.id in self._deletion_tasks:
            return

        task = asyncio.create_task(self._delete_when_idle(channel))
        self._deletion_tasks[channel.id] = task
        task.add_done_callback(lambda done_task, channel_id=channel.id: self._deletion_tasks.pop(channel_id, None))

    def _cancel_deletion(self, channel_id: int) -> None:
        task = self._deletion_tasks.pop(channel_id, None)
        if task is not None:
            task.cancel()

    async def _delete_when_idle(self, channel: discord.VoiceChannel) -> None:
        try:
            await asyncio.sleep(self._idle_timeout_seconds)
            existing_channel = channel.guild.get_channel(channel.id)
            if not isinstance(existing_channel, discord.VoiceChannel):
                return
            if existing_channel.members:
                return
            await existing_channel.delete(reason="Suppression salon vocal temporaire inactif.")
            logger.info("Deleted idle temp voice channel %s.", channel.id)
        except asyncio.CancelledError:
            raise
        except discord.NotFound:
            return
        except discord.Forbidden:
            logger.warning("Missing permissions to delete idle temp voice channel %s.", channel.id)
        except discord.HTTPException as exc:
            logger.warning("HTTP error while deleting idle temp voice channel %s: %s", channel.id, exc)

    @tasks.loop(minutes=1)
    async def voice_check_loop(self) -> None:
        try:
            for guild in self.bot.guilds:
                config = await self._service.get_config(guild.id)
                if not config.is_complete:
                    continue

                for channel in guild.voice_channels:
                    if self._service.should_schedule_deletion(channel, config=config):
                        self._schedule_deletion(channel)
                    elif self._service.should_cancel_deletion(channel, config=config):
                        self._cancel_deletion(channel.id)
        except Exception:
            logger.exception("Temp voice check task failed.")

    @voice_check_loop.before_loop
    async def before_voice_check_loop(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    temp_voice_service = getattr(bot, "temp_voice_service", None)
    if temp_voice_service is None:
        logger.error("temp_voice_service is not initialized. TempVoiceCog will not be loaded.")
        return
    await bot.add_cog(TempVoiceCog(bot, temp_voice_service))
    logger.info("TempVoiceCog loaded.")
