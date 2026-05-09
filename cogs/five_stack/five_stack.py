from __future__ import annotations

import asyncio
import logging
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands, tasks

from cogs.five_stack.presenters import (
    build_global_match_history_embed,
    build_leaderboard_embed,
    build_match_history_embed,
    build_player_stats_embed,
    build_queue_embed,
    build_role_counters_embed,
    build_server_stats_embed,
    build_team_embed,
    queue_status_message,
    team_status_message,
)
from cogs.five_stack.services import FiveStackService
from cogs.five_stack.views import QueueView, TeamPublicView
from database.services.five_stack_service import FiveStackTeamInfo

logger = logging.getLogger(__name__)

DEFAULT_MATCHMAKING_CATEGORY = "Matchmaking"
TEAM_RETENTION_HOURS = 24


class FiveStackCog(commands.Cog):
    team_group = app_commands.Group(name="team", description="Gestion des equipes five-stack")
    matchmaking_group = app_commands.Group(name="matchmaking", description="Stats et historique matchmaking")

    def __init__(self, bot: commands.Bot, service: FiveStackService) -> None:
        self.bot = bot
        self._service = service
        self._views_reloaded = False
        self._server_locks: dict[int, asyncio.Lock] = {}
        self.process_queue_task_loop.start()
        self.stale_task.start()
        self.cleanup_teams_task.start()
        self.voice_cleaner_task.start()
        logger.info("FiveStackCog initialized.")

    def cog_unload(self) -> None:
        for task_loop in (
            self.process_queue_task_loop,
            self.stale_task,
            self.cleanup_teams_task,
            self.voice_cleaner_task,
        ):
            if task_loop.is_running():
                task_loop.cancel()
        self._server_locks.clear()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if self._views_reloaded:
            return
        self._views_reloaded = True
        await self._reload_persistent_views()

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        team = await self._service.get_user_team(guild_id=member.guild.id, discord_member_id=member.id)
        if team is None:
            return
        if team.team.leader_discord_id == member.id:
            await self._delete_team_resources(member.guild, team)
            await self._service.delete_team(
                guild_id=member.guild.id,
                code=team.team.code,
                actor_discord_id=team.team.leader_discord_id,
            )
            return
        await self._service.leave_team(guild_id=member.guild.id, discord_member_id=member.id)

    @commands.command(name="start_queue")
    @commands.has_permissions(administrator=True)
    async def start_queue(self, ctx: commands.Context) -> None:
        if not ctx.guild:
            return
        entries = await self._service.list_queue(ctx.guild.id)
        message = await ctx.send(embed=build_queue_embed(entries), view=QueueView(self))
        await self._service.save_queue_message(
            guild_id=ctx.guild.id,
            guild_name=ctx.guild.name,
            channel_id=message.channel.id,
            message_id=message.id,
        )
        await ctx.send("Queue initialisee.")

    @commands.command(name="role_counters")
    async def role_counters(self, ctx: commands.Context) -> None:
        if not ctx.guild:
            return
        entries = await self._service.list_queue(ctx.guild.id)
        counts = self._service.role_counts(entries)
        await ctx.send(embed=build_role_counters_embed(counts))

    @team_group.command(name="create", description="Creer une equipe five-stack.")
    @app_commands.describe(visibility="Visibilite de l'equipe.")
    async def team_create(
        self,
        interaction: discord.Interaction,
        visibility: Literal["public", "private"] = "public",
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send("Cette commande doit etre executee dans un serveur.", ephemeral=True)
            return

        result = await self._service.create_team(
            guild_id=interaction.guild.id,
            guild_name=interaction.guild.name,
            leader_discord_id=interaction.user.id,
            visibility=visibility,
        )
        if result.team is None:
            await interaction.followup.send(team_status_message(result.status), ephemeral=True)
            return

        await self._create_team_thread(interaction.guild, result.team)
        await interaction.followup.send(
            team_status_message(result.status, code=result.team.team.code),
            embed=build_team_embed(result.team),
            ephemeral=True,
        )

    @team_group.command(name="join", description="Rejoindre une equipe avec son code.")
    @app_commands.describe(code="Code de l'equipe.")
    async def team_join(self, interaction: discord.Interaction, code: str) -> None:
        await self.handle_join_team(interaction, code=code)

    @team_group.command(name="leave", description="Quitter votre equipe.")
    async def team_leave(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("Serveur introuvable.", ephemeral=True)
            return
        result = await self._service.leave_team(
            guild_id=interaction.guild.id,
            discord_member_id=interaction.user.id,
        )
        if result.team and not result.team.member_ids:
            await self._delete_team_resources(interaction.guild, result.team)
        await interaction.followup.send(team_status_message(result.status), ephemeral=True)

    @team_group.command(name="kick", description="Retirer un membre de votre equipe.")
    @app_commands.describe(member="Membre a retirer.", code="Code de l'equipe, optionnel.")
    async def team_kick(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        code: str | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("Serveur introuvable.", ephemeral=True)
            return
        team = await self._resolve_team_for_action(interaction.guild.id, interaction.user.id, code)
        if team is None:
            await interaction.followup.send("Equipe introuvable.", ephemeral=True)
            return
        result = await self._service.kick_member(
            guild_id=interaction.guild.id,
            code=team.team.code,
            actor_discord_id=interaction.user.id,
            target_discord_id=member.id,
        )
        await interaction.followup.send(team_status_message(result.status), ephemeral=True)

    @team_group.command(name="delete", description="Supprimer votre equipe.")
    @app_commands.describe(code="Code de l'equipe, optionnel.")
    async def team_delete(self, interaction: discord.Interaction, code: str | None = None) -> None:
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("Serveur introuvable.", ephemeral=True)
            return
        team = await self._resolve_team_for_action(interaction.guild.id, interaction.user.id, code)
        if team is None:
            await interaction.followup.send("Equipe introuvable.", ephemeral=True)
            return
        result = await self._service.delete_team(
            guild_id=interaction.guild.id,
            code=team.team.code,
            actor_discord_id=interaction.user.id,
        )
        if result.team:
            await self._delete_team_resources(interaction.guild, result.team)
        await interaction.followup.send(team_status_message(result.status), ephemeral=True)

    @team_group.command(name="list", description="Lister les equipes actives.")
    async def team_list(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("Serveur introuvable.", ephemeral=True)
            return
        teams = await self._service.list_teams(interaction.guild.id)
        if not teams:
            await interaction.followup.send("Aucune equipe active.", ephemeral=True)
            return
        lines = [f"`{team.team.code}` - {len(team.member_ids)}/5 - <@{team.team.leader_discord_id}>" for team in teams[:20]]
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @team_group.command(name="info", description="Afficher une equipe.")
    @app_commands.describe(code="Code de l'equipe.")
    async def team_info(self, interaction: discord.Interaction, code: str) -> None:
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("Serveur introuvable.", ephemeral=True)
            return
        team = await self._service.get_team(guild_id=interaction.guild.id, code=code)
        if team is None:
            await interaction.followup.send("Equipe introuvable.", ephemeral=True)
            return
        await interaction.followup.send(embed=build_team_embed(team), ephemeral=True)

    @matchmaking_group.command(name="stats", description="Voir vos statistiques de matchmaking.")
    @app_commands.describe(member="Membre cible, vous par defaut.")
    async def matchmaking_stats(self, interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("Serveur introuvable.", ephemeral=True)
            return
        target = member or interaction.user
        stats = await self._service.get_player_stats(guild_id=interaction.guild.id, discord_member_id=target.id)
        await interaction.followup.send(embed=build_player_stats_embed(target, stats), ephemeral=True)

    @matchmaking_group.command(name="history", description="Voir l'historique matchmaking.")
    @app_commands.describe(member="Membre cible, vous par defaut.", limit="Nombre de matchs.")
    async def matchmaking_history(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
        limit: app_commands.Range[int, 1, 25] = 10,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("Serveur introuvable.", ephemeral=True)
            return
        if member:
            bundles = await self._service.get_player_match_history(
                guild_id=interaction.guild.id,
                discord_member_id=member.id,
                limit=limit,
            )
            await interaction.followup.send(embed=build_match_history_embed(member, bundles), ephemeral=True)
            return
        rows = await self._service.get_match_history(guild_id=interaction.guild.id, limit=limit)
        await interaction.followup.send(embed=build_global_match_history_embed(rows), ephemeral=True)

    @matchmaking_group.command(name="server", description="Voir les statistiques du serveur.")
    async def matchmaking_server(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("Serveur introuvable.", ephemeral=True)
            return
        stats = await self._service.get_server_stats(interaction.guild.id)
        await interaction.followup.send(embed=build_server_stats_embed(interaction.guild, stats), ephemeral=True)

    @matchmaking_group.command(name="leaderboard", description="Voir le classement matchmaking.")
    async def matchmaking_leaderboard(
        self,
        interaction: discord.Interaction,
        category: Literal["matches", "wait_time"] = "matches",
        limit: app_commands.Range[int, 5, 25] = 10,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("Serveur introuvable.", ephemeral=True)
            return
        rows = await self._service.get_leaderboard(guild_id=interaction.guild.id, category=category, limit=limit)
        await interaction.followup.send(embed=build_leaderboard_embed(interaction.guild, rows, category=category), ephemeral=True)

    @matchmaking_group.command(name="feedback", description="Donner un feedback sur un match.")
    async def matchmaking_feedback(
        self,
        interaction: discord.Interaction,
        match_id: int,
        rating: app_commands.Range[int, 1, 5],
        comment: str | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        await self._service.save_feedback(
            match_id=match_id,
            reporter_id=interaction.user.id,
            rating=rating,
            feedback_type="general",
            comment=comment,
        )
        await interaction.followup.send("Feedback enregistre.", ephemeral=True)

    async def handle_join_solo_queue(self, interaction: discord.Interaction, *, desired_team_size: int) -> None:
        await self._handle_join_queue(interaction, mode="solo", desired_team_size=desired_team_size)

    async def handle_join_team_queue(self, interaction: discord.Interaction, *, desired_team_size: int) -> None:
        await self._handle_join_queue(interaction, mode="team", desired_team_size=desired_team_size)

    async def handle_leave_queue(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("Serveur introuvable.", ephemeral=True)
            return
        removed = await self._service.remove_from_queue(
            guild_id=interaction.guild.id,
            discord_member_id=interaction.user.id,
        )
        await self._refresh_queue_message(interaction.guild)
        await interaction.followup.send(queue_status_message("left") if removed else "Vous n'etiez pas dans la queue.", ephemeral=True)

    async def handle_join_team(self, interaction: discord.Interaction, *, code: str) -> None:
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("Serveur introuvable.", ephemeral=True)
            return
        result = await self._service.join_team(
            guild_id=interaction.guild.id,
            guild_name=interaction.guild.name,
            code=code,
            discord_member_id=interaction.user.id,
        )
        await interaction.followup.send(
            team_status_message(result.status),
            embed=build_team_embed(result.team) if result.team else None,
            ephemeral=True,
        )

    @tasks.loop(seconds=15)
    async def process_queue_task_loop(self) -> None:
        proposals = await self._service.find_match_proposals()
        for proposal in proposals:
            guild = self.bot.get_guild(proposal.guild_id)
            if guild is None:
                continue
            lock = self._server_locks.setdefault(guild.id, asyncio.Lock())
            async with lock:
                await self._create_match(guild, proposal)

    @process_queue_task_loop.before_loop
    async def before_process_queue(self) -> None:
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=1)
    async def stale_task(self) -> None:
        converted, removed_ids = await self._service.cleanup_queue()
        if not converted and not removed_ids:
            return
        for guild in self.bot.guilds:
            await self._refresh_queue_message(guild)
        for member_id in removed_ids:
            await self._safe_dm(member_id, "Votre inscription a la queue a expire apres 10 minutes.")

    @stale_task.before_loop
    async def before_stale(self) -> None:
        await self.bot.wait_until_ready()

    @tasks.loop(hours=1)
    async def cleanup_teams_task(self) -> None:
        for team in await self._service.list_old_teams(hours=TEAM_RETENTION_HOURS):
            guild = self.bot.get_guild(team.team.guild_id)
            if guild is None:
                continue
            await self._delete_team_resources(guild, team)
            await self._service.delete_team(
                guild_id=guild.id,
                code=team.team.code,
                actor_discord_id=team.team.leader_discord_id,
            )

    @cleanup_teams_task.before_loop
    async def before_cleanup_teams(self) -> None:
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=5)
    async def voice_cleaner_task(self) -> None:
        for guild in self.bot.guilds:
            category_id = await self._service.get_voice_cleaner_category_id(guild.id)
            afk_id = await self._service.get_voice_cleaner_afk_id(guild.id)
            category = guild.get_channel(category_id) if category_id else None
            if not isinstance(category, discord.CategoryChannel):
                continue
            for channel in category.voice_channels:
                if channel.id == afk_id:
                    continue
                if not channel.members:
                    try:
                        await channel.delete(reason="Five-stack voice cleaner")
                    except discord.HTTPException:
                        logger.exception("Could not delete empty voice channel %s.", channel.id)

    @voice_cleaner_task.before_loop
    async def before_voice_cleaner(self) -> None:
        await self.bot.wait_until_ready()

    async def _handle_join_queue(self, interaction: discord.Interaction, *, mode: str, desired_team_size: int) -> None:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send("Serveur introuvable.", ephemeral=True)
            return
        if desired_team_size not in {0, 2, 3, 5}:
            await interaction.followup.send(queue_status_message("invalid_size"), ephemeral=True)
            return

        role_ids = {role.id for role in interaction.user.roles}
        if mode == "solo":
            data = await self._service.build_solo_queue_data(
                guild_id=interaction.guild.id,
                guild_name=interaction.guild.name,
                member_id=interaction.user.id,
                role_ids=role_ids,
                desired_team_size=desired_team_size,
            )
            missing_status = "missing_valorant"
        else:
            data = await self._service.build_team_queue_data(
                guild_id=interaction.guild.id,
                guild_name=interaction.guild.name,
                leader_id=interaction.user.id,
                leader_role_ids=role_ids,
                desired_team_size=desired_team_size,
            )
            missing_status = "missing_team"

        if data is None:
            await interaction.followup.send(queue_status_message(missing_status), ephemeral=True)
            return

        await self._service.add_queue_entry(data)
        await self._refresh_queue_message(interaction.guild)
        await interaction.followup.send(queue_status_message("joined"), ephemeral=True)

    async def _create_match(self, guild: discord.Guild, proposal) -> None:
        channel = await self._create_match_voice_channel(guild, proposal.member_ids)
        match_code = self._service.generate_match_code()
        match = await self._service.record_match(
            proposal,
            match_code=match_code,
            voice_channel_id=channel.id if channel else None,
        )
        await self._refresh_queue_message(guild)
        message = (
            f"Match `{match.match_code}` trouve en {proposal.team_size}v{proposal.team_size}."
            + (f" Salon vocal: {channel.mention}" if channel else "")
        )
        for member_id in proposal.member_ids:
            await self._safe_dm(member_id, message)

    async def _create_match_voice_channel(self, guild: discord.Guild, member_ids: tuple[int, ...]) -> discord.VoiceChannel | None:
        category = await self._resolve_matchmaking_category(guild)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
        }
        if guild.me:
            overwrites[guild.me] = discord.PermissionOverwrite(view_channel=True, connect=True, manage_channels=True)
        for member_id in member_ids:
            member = guild.get_member(member_id)
            if member:
                overwrites[member] = discord.PermissionOverwrite(view_channel=True, connect=True)
        try:
            return await guild.create_voice_channel(
                name=f"Five Stack {len(member_ids)}v{len(member_ids)}",
                category=category,
                overwrites=overwrites,
                reason="Five-stack matchmaking",
            )
        except discord.HTTPException:
            logger.exception("Could not create five-stack voice channel.")
            return None

    async def _resolve_matchmaking_category(self, guild: discord.Guild) -> discord.CategoryChannel | None:
        category_id = await self._service.get_matchmaking_category_id(guild.id)
        configured = guild.get_channel(category_id) if category_id else None
        if isinstance(configured, discord.CategoryChannel):
            return configured
        existing = discord.utils.get(guild.categories, name=DEFAULT_MATCHMAKING_CATEGORY)
        if existing:
            return existing
        try:
            return await guild.create_category(DEFAULT_MATCHMAKING_CATEGORY, reason="Five-stack matchmaking")
        except discord.HTTPException:
            logger.exception("Could not create matchmaking category.")
            return None

    async def _create_team_thread(self, guild: discord.Guild, team: FiveStackTeamInfo) -> None:
        forum_id = await self._service.get_team_forum_channel_id(guild.id)
        channel = guild.get_channel(forum_id) if forum_id else None
        if not isinstance(channel, discord.ForumChannel):
            return
        content = f"Equipe creee par <@{team.team.leader_discord_id}>.\nCode: ||{team.team.code}||"
        view = TeamPublicView(self, team.team.code) if team.team.visibility == "public" else None
        try:
            thread_with_message = await channel.create_thread(
                name=f"Equipe {team.team.code}",
                content=content,
                embed=build_team_embed(team),
                view=view,
            )
            await self._service.set_team_thread(
                guild_id=guild.id,
                code=team.team.code,
                forum_channel_id=channel.id,
                thread_id=thread_with_message.thread.id,
            )
        except discord.HTTPException:
            logger.exception("Could not create team thread for %s.", team.team.code)

    async def _delete_team_resources(self, guild: discord.Guild, team: FiveStackTeamInfo) -> None:
        for channel_id in (team.team.thread_id, team.team.voice_channel_id):
            channel = guild.get_channel(channel_id) if channel_id else None
            if channel is None:
                continue
            try:
                await channel.delete(reason="Five-stack team cleanup")
            except discord.HTTPException:
                logger.exception("Could not delete team resource %s.", channel_id)

    async def _resolve_team_for_action(self, guild_id: int, actor_id: int, code: str | None) -> FiveStackTeamInfo | None:
        if code:
            return await self._service.get_team(guild_id=guild_id, code=code)
        return await self._service.get_user_team(guild_id=guild_id, discord_member_id=actor_id)

    async def _refresh_queue_message(self, guild: discord.Guild) -> None:
        persistent = await self._service.get_queue_message(guild.id)
        if persistent is None:
            return
        channel = guild.get_channel(persistent.channel_id)
        if not channel or not hasattr(channel, "fetch_message"):
            return
        try:
            message = await channel.fetch_message(persistent.message_id)
            entries = await self._service.list_queue(guild.id)
            await message.edit(embed=build_queue_embed(entries), view=QueueView(self))
        except (discord.NotFound, discord.Forbidden):
            return
        except discord.HTTPException:
            logger.exception("Could not refresh queue message for guild %s.", guild.id)

    async def _reload_persistent_views(self) -> None:
        for guild in self.bot.guilds:
            queue_message = await self._service.get_queue_message(guild.id)
            if queue_message:
                self.bot.add_view(QueueView(self), message_id=queue_message.message_id)
            for team in await self._service.list_teams(guild.id):
                if team.team.thread_id and team.team.visibility == "public":
                    self.bot.add_view(TeamPublicView(self, team.team.code))

    async def _safe_dm(self, discord_id: int, content: str) -> None:
        try:
            user = self.bot.get_user(discord_id) or await self.bot.fetch_user(discord_id)
            await user.send(content)
        except Exception:
            logger.debug("Could not DM user %s.", discord_id)


async def setup(bot: commands.Bot) -> None:
    service = getattr(bot, "five_stack_service", None)
    if service is None:
        logger.error("five_stack_service is not initialized. FiveStackCog will not be loaded.")
        return
    await bot.add_cog(FiveStackCog(bot, service))
    logger.info("FiveStackCog loaded.")
