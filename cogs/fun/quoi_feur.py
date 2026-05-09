from __future__ import annotations

import asyncio
import logging

import discord
from discord.ext import commands

from cogs.fun.services import QuoiResponderService

logger = logging.getLogger(__name__)


class QuoiFeurCog(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
        responder_service: QuoiResponderService | None = None,
    ) -> None:
        self.bot = bot
        self._service = responder_service or QuoiResponderService()
        self._lock = asyncio.Lock()
        logger.info("QuoiFeurCog initialized.")

    def cog_unload(self) -> None:
        self._service.clear()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return

        if not self._service.matches_trigger(message.content or ""):
            return

        async with self._lock:
            if not self._service.allow_response(message.author.id):
                return

        emoji = discord.utils.get(message.guild.emojis, name="pepe_clown")
        emoji_text = str(emoji) if emoji else ":pepe_clown:"
        await message.channel.send(self._service.build_response(emoji_text))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(QuoiFeurCog(bot))
    logger.info("QuoiFeurCog loaded.")
