from __future__ import annotations

import logging

import discord
from discord.ext import commands

from cogs.file_counter.presenters import build_file_counter_embed
from cogs.file_counter.services import FILE_COUNTER_CHANNEL_KEY, FileCounterService
from cogs.file_counter.views import FileCounterView

logger = logging.getLogger(__name__)


class FileCounterCog(commands.Cog):
    def __init__(self, bot: commands.Bot, file_counter_service: FileCounterService) -> None:
        self.bot = bot
        self._service = file_counter_service
        self.bot.add_view(FileCounterView(self))
        logger.info("FileCounterCog initialized.")

    @commands.command(name="init_counter")
    @commands.has_permissions(administrator=True)
    async def init_counter(self, ctx: commands.Context) -> None:
        if not ctx.guild:
            await ctx.send("Cette commande doit etre executee dans un serveur.", delete_after=10)
            return

        channel_id = await self._service.get_configured_channel_id(ctx.guild.id)
        if channel_id is None:
            await ctx.send(
                f"Configurez d'abord le salon `{FILE_COUNTER_CHANNEL_KEY}` avec `/salon`.",
                delete_after=15,
            )
            return

        channel = ctx.guild.get_channel(channel_id) or self.bot.get_channel(channel_id)
        if not channel or not hasattr(channel, "send") or not hasattr(channel, "fetch_message"):
            await ctx.send("Le salon configure pour le compteur est introuvable.", delete_after=10)
            return

        existing = await self._service.get_counter(ctx.guild.id, channel_id)
        if existing:
            try:
                old_message = await channel.fetch_message(existing.message_id)
                await old_message.delete()
            except discord.NotFound:
                pass
            except discord.Forbidden:
                await ctx.send("Je n'ai pas la permission de supprimer l'ancien compteur.", delete_after=10)
                return

        message = await channel.send(
            embed=build_file_counter_embed(added_count=0, completed_count=0),
            view=FileCounterView(self),
        )
        await self._service.reset_counter(
            guild_id=ctx.guild.id,
            guild_name=ctx.guild.name,
            channel_id=message.channel.id,
            message_id=message.id,
        )
        await ctx.send("Compteur de fichiers initialise.", delete_after=10)

    async def handle_counter_increment(self, interaction: discord.Interaction, action: str) -> None:
        if not interaction.guild or interaction.channel_id is None:
            await interaction.response.send_message(
                "Cette action doit etre effectuee dans un serveur.",
                ephemeral=True,
            )
            return

        if action == "add":
            counter = await self._service.increment_added(
                guild_id=interaction.guild.id,
                channel_id=interaction.channel_id,
            )
        elif action == "complete":
            counter = await self._service.increment_completed(
                guild_id=interaction.guild.id,
                channel_id=interaction.channel_id,
            )
        else:
            counter = None

        if counter is None:
            await interaction.response.send_message(
                "Ce compteur n'est plus configure. Relancez `!init_counter`.",
                ephemeral=True,
            )
            return

        if interaction.message and interaction.message.id != counter.message_id:
            await interaction.response.send_message(
                "Ce message n'est plus le compteur actif.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        if interaction.message:
            await interaction.message.edit(
                embed=build_file_counter_embed(
                    added_count=counter.added_count,
                    completed_count=counter.completed_count,
                ),
                view=FileCounterView(self),
            )

    @init_counter.error
    async def init_counter_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("Vous n'avez pas les permissions necessaires.", delete_after=10)
            return
        logger.exception("init_counter failed: %s", error)
        await ctx.send("Une erreur est survenue lors de l'execution de la commande.", delete_after=10)


async def setup(bot: commands.Bot) -> None:
    file_counter_service = getattr(bot, "file_counter_service", None)
    if file_counter_service is None:
        logger.error("file_counter_service is not initialized. FileCounterCog will not be loaded.")
        return
    await bot.add_cog(FileCounterCog(bot, file_counter_service))
    logger.info("FileCounterCog loaded.")
