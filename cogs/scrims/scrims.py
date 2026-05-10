from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks

from cogs.scrims.presenters import (
    build_scrim_creation_message,
    build_scrim_embed,
    join_status_message,
    leave_status_message,
)
from cogs.scrims.services import ScrimService
from cogs.scrims.views import CreateScrimView, ScrimView
from database.services.scrims_service import ScrimInfo

logger = logging.getLogger(__name__)

PARIS_TZ = ZoneInfo("Europe/Paris")
SCRIM_END_GRACE_SECONDS = 60


class ScrimCog(commands.Cog):
    def __init__(self, bot: commands.Bot, service: ScrimService) -> None:
        self.bot = bot
        self._service = service
        self._views_reloaded = False
        self._ending_scrims: set[int] = set()
        self.scrim_end_checker.start()
        logger.info("ScrimCog initialized.")

    def cog_unload(self) -> None:
        if self.scrim_end_checker.is_running():
            self.scrim_end_checker.cancel()
        self._ending_scrims.clear()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if self._views_reloaded:
            return
        self._views_reloaded = True
        await self._reload_persistent_views()

    @commands.command(name="init_scrim")
    @commands.has_permissions(administrator=True)
    async def init_scrim(self, ctx: commands.Context) -> None:
        if not ctx.guild:
            return

        message = await ctx.send(
            build_scrim_creation_message(),
            view=CreateScrimView(self),
        )
        await self._service.save_creation_message(
            guild_id=ctx.guild.id,
            guild_name=ctx.guild.name,
            channel_id=message.channel.id,
            message_id=message.id,
        )

    @init_scrim.error
    async def init_scrim_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(
                "Vous devez etre administrateur pour initialiser le module scrim.",
                delete_after=10,
            )
            return
        raise error

    @tasks.loop(minutes=1)
    async def scrim_end_checker(self) -> None:
        try:
            due_scrims = await self._service.list_due_scrims(
                now=datetime.now(PARIS_TZ) - timedelta(seconds=SCRIM_END_GRACE_SECONDS)
            )
            for scrim in due_scrims:
                if scrim.id in self._ending_scrims:
                    continue
                self._ending_scrims.add(scrim.id)
                try:
                    await self._complete_scrim(scrim)
                except Exception:
                    logger.exception("Could not complete scrim %s.", scrim.id)
                finally:
                    self._ending_scrims.discard(scrim.id)
        except Exception:
            logger.exception("Scrim end checker task failed.")

    @scrim_end_checker.before_loop
    async def before_scrim_end_checker(self) -> None:
        await self.bot.wait_until_ready()

    async def handle_create_scrim_submit(self, interaction: discord.Interaction, modal) -> None:
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild or not interaction.channel:
            await interaction.followup.send("Cette action doit etre faite dans un serveur.", ephemeral=True)
            return

        if not await self._check_rules(interaction):
            return

        try:
            data = self._service.parse_creation_data(
                date_raw=str(modal.date.value),
                time_raw=str(modal.time.value),
                map_name=str(modal.map_name.value),
                rank_name=str(modal.rank_name.value),
                notes=str(modal.notes.value or ""),
            )
        except ValueError:
            await interaction.followup.send("Format invalide: utilisez JJ/MM/YYYY et HH:MM.", ephemeral=True)
            return

        scrim = await self._service.create_scrim(
            guild_id=interaction.guild.id,
            guild_name=interaction.guild.name,
            creator_discord_id=interaction.user.id,
            data=data,
        )

        message = await interaction.channel.send(
            embed=build_scrim_embed(scrim),
            view=ScrimView(self, scrim.id),
        )
        scrim = await self._service.save_scrim_message(
            scrim_id=scrim.id,
            channel_id=message.channel.id,
            message_id=message.id,
        ) or scrim
        await interaction.followup.send("Scrim cree avec succes.", ephemeral=True)

    async def handle_join_team(self, interaction: discord.Interaction, scrim_id: int, team: str) -> None:
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("Serveur introuvable.", ephemeral=True)
            return

        if not await self._check_rules(interaction):
            return

        result = await self._service.join_team(
            guild_id=interaction.guild.id,
            guild_name=interaction.guild.name,
            scrim_id=scrim_id,
            discord_user_id=interaction.user.id,
            team=team,
        )
        if result.scrim and interaction.message:
            await interaction.message.edit(embed=build_scrim_embed(result.scrim), view=ScrimView(self, scrim_id))

        team_label = "l'equipe 1" if team == "team1" else "l'equipe 2"
        await interaction.followup.send(join_status_message(result.status, team_label=team_label), ephemeral=True)

    async def handle_leave_scrim(self, interaction: discord.Interaction, scrim_id: int) -> None:
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("Serveur introuvable.", ephemeral=True)
            return

        if not await self._check_rules(interaction):
            return

        result = await self._service.leave_scrim(
            guild_id=interaction.guild.id,
            scrim_id=scrim_id,
            discord_user_id=interaction.user.id,
        )
        if result.scrim and interaction.message:
            await interaction.message.edit(embed=build_scrim_embed(result.scrim), view=ScrimView(self, scrim_id))

        await interaction.followup.send(leave_status_message(result.status), ephemeral=True)

    async def _reload_persistent_views(self) -> None:
        for guild in self.bot.guilds:
            creation_message = await self._service.get_creation_message(guild.id)
            if creation_message:
                self.bot.add_view(CreateScrimView(self), message_id=creation_message.message_id)

            for scrim in await self._service.list_active_scrims(guild.id):
                if scrim.message_id:
                    self.bot.add_view(ScrimView(self, scrim.id), message_id=scrim.message_id)

    async def _check_rules(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            await interaction.followup.send("Serveur introuvable.", ephemeral=True)
            return False

        accepted = await self._service.has_accepted_rules(
            guild_id=interaction.guild.id,
            discord_user_id=interaction.user.id,
        )
        if not accepted:
            await interaction.followup.send("Vous devez accepter le reglement avant d'utiliser les scrims.", ephemeral=True)
            return False
        return True

    async def _complete_scrim(self, scrim: ScrimInfo) -> None:
        await self._delete_scrim_message(scrim)
        await self._dm_participants(scrim)
        await self._service.mark_completed(scrim.id)
        logger.info("Scrim %s completed.", scrim.id)

    async def _delete_scrim_message(self, scrim: ScrimInfo) -> None:
        if not scrim.channel_id or not scrim.message_id:
            return

        channel = self.bot.get_channel(scrim.channel_id)
        if channel is None or not hasattr(channel, "fetch_message"):
            return

        try:
            message = await channel.fetch_message(scrim.message_id)
            await message.delete()
        except discord.NotFound:
            return
        except discord.HTTPException:
            logger.exception("Could not delete scrim message %s.", scrim.message_id)

    async def _dm_participants(self, scrim: ScrimInfo) -> None:
        for discord_id in scrim.participant_discord_ids:
            try:
                user = self.bot.get_user(discord_id) or await self.bot.fetch_user(discord_id)
                await user.send("Rappel : le scrim auquel vous etes inscrit vient de debuter. **Perfect Team**")
            except Exception:
                logger.debug("Could not DM scrim participant %s.", discord_id)


async def setup(bot: commands.Bot) -> None:
    service = getattr(bot, "scrim_service", None)
    if service is None:
        logger.error("scrim_service is not initialized. ScrimCog will not be loaded.")
        return

    await bot.add_cog(ScrimCog(bot, service))
    logger.info("ScrimCog loaded.")
