# cogs/file_counter/file_counter.py

import logging

import discord
from discord.ext import commands

from cogs.file_counter.services.file_counter_service import FileCounterService

logger = logging.getLogger(__name__)

# ID du salon de suivi des fichiers (configurable ultérieurement via guild_channels)
FILE_COUNTER_CHANNEL_ID = 1136359641899614408


class CounterView(discord.ui.View):
    def __init__(self, service: FileCounterService, guild_id: int, channel_id: int,
                 message_id: int, ajouter_count: int, terminer_count: int):
        super().__init__(timeout=None)
        self._service = service
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.message_id = message_id
        self.ajouter_count = ajouter_count
        self.terminer_count = terminer_count

    @discord.ui.button(label="Ajouter", style=discord.ButtonStyle.green, custom_id="file_counter:ajouter")
    async def ajouter_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild:
            await interaction.response.send_message("Serveur uniquement.", ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        updated = await self._service.increment(self.guild_id, self.channel_id, ajouter=True)
        if updated:
            self.ajouter_count = updated.ajouter_count
            self.terminer_count = updated.terminer_count
            await self._update_embed(interaction)
        else:
            await interaction.followup.send("Erreur lors de la mise à jour.", ephemeral=True)

    @discord.ui.button(label="Terminer", style=discord.ButtonStyle.blurple, custom_id="file_counter:terminer")
    async def terminer_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild:
            await interaction.response.send_message("Serveur uniquement.", ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        updated = await self._service.increment(self.guild_id, self.channel_id, terminer=True)
        if updated:
            self.ajouter_count = updated.ajouter_count
            self.terminer_count = updated.terminer_count
            await self._update_embed(interaction)
        else:
            await interaction.followup.send("Erreur lors de la mise à jour.", ephemeral=True)

    async def _update_embed(self, interaction: discord.Interaction):
        percentage = _calc_percentage(self.terminer_count, self.ajouter_count)
        embed = _build_embed(self.ajouter_count, self.terminer_count, percentage)
        try:
            channel = interaction.guild.get_channel(self.channel_id)
            if not channel:
                return
            message = await channel.fetch_message(self.message_id)
            await message.edit(embed=embed, view=self)
        except Exception as e:
            logger.error(f"Erreur mise à jour embed compteur: {e}")


class FileCounterCog(commands.Cog):
    """Cog pour gérer le suivi des fichiers avec des boutons interactifs."""

    def __init__(self, bot: commands.Bot, service: FileCounterService):
        self.bot = bot
        self._service = service
        self.channel_id = FILE_COUNTER_CHANNEL_ID

    @commands.Cog.listener()
    async def on_ready(self):
        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            logger.error(f"Salon {self.channel_id} introuvable.")
            return

        guild = channel.guild
        if not guild:
            return

        data = await self._service.get_counter(guild.id, self.channel_id)
        if data:
            try:
                message = await channel.fetch_message(data.message_id)
                percentage = _calc_percentage(data.terminer_count, data.ajouter_count)
                embed = _build_embed(data.ajouter_count, data.terminer_count, percentage)
                view = CounterView(
                    self._service, guild.id, self.channel_id,
                    data.message_id, data.ajouter_count, data.terminer_count,
                )
                await message.edit(embed=embed, view=view)
                self.bot.add_view(view)
                logger.info("Message compteur existant rechargé.")
            except discord.NotFound:
                logger.warning("Message compteur non trouvé, création d'un nouveau.")
                await self._send_new_counter(channel, guild)
        else:
            await self._send_new_counter(channel, guild)

    @commands.command(name="init_counter")
    @commands.has_permissions(administrator=True)
    async def init_counter(self, ctx: commands.Context):
        """Réinitialise le compteur de fichiers."""
        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            await ctx.send("Salon introuvable.", delete_after=10)
            return

        guild = ctx.guild
        data = await self._service.get_counter(guild.id, self.channel_id)
        if data and data.message_id:
            try:
                old_msg = await channel.fetch_message(data.message_id)
                await old_msg.delete()
            except discord.NotFound:
                pass

        message = await self._send_counter_message(channel, guild.id, 0, 0)
        if data:
            await self._service.reset(guild.id, self.channel_id, message.id)
        else:
            await self._service.create_or_update(guild.id, guild.name, self.channel_id, message.id)

        await ctx.send("Compteur réinitialisé.", delete_after=10)

    async def _send_new_counter(self, channel, guild):
        message = await self._send_counter_message(channel, guild.id, 0, 0)
        await self._service.create_or_update(guild.id, guild.name, self.channel_id, message.id)

    async def _send_counter_message(self, channel, guild_id: int, ajouter: int, terminer: int) -> discord.Message:
        percentage = _calc_percentage(terminer, ajouter)
        embed = _build_embed(ajouter, terminer, percentage)
        view = CounterView(self._service, guild_id, self.channel_id, 0, ajouter, terminer)
        message = await channel.send(embed=embed, view=view)
        view.message_id = message.id
        self.bot.add_view(view)
        return message


def _calc_percentage(terminer: int, ajouter: int) -> float:
    if ajouter > 0:
        return min(round((terminer / ajouter) * 100, 1), 100.0)
    return 0.0


def _build_embed(ajouter: int, terminer: int, percentage: float) -> discord.Embed:
    return discord.Embed(
        title="Suivi des Fichiers",
        color=discord.Color.blue(),
        description=(
            f"**Fichier total**: {ajouter}\n"
            f"**Fichier terminer**: {terminer}\n"
            f"**Pourcentage de completion**: {percentage}%"
        ),
    )


async def setup(bot: commands.Bot):
    from database.services.file_counters_service import FileCountersService
    counters_db_svc = FileCountersService(bot.db)
    service = FileCounterService(counters_db_svc)
    await bot.add_cog(FileCounterCog(bot, service))
    logger.info("FileCounterCog chargé.")
