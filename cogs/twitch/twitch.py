from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from cogs.twitch.presenters import (
    TwitchLiveNotification,
    build_twitch_live_embed,
    format_streamer_list,
)
from cogs.twitch.services import TwitchNotificationService
from integrations.twitch.service import TwitchService as TwitchApiService

logger = logging.getLogger(__name__)

ACTION_CHOICES = [
    app_commands.Choice(name="Ajouter", value="add"),
    app_commands.Choice(name="Supprimer", value="remove"),
    app_commands.Choice(name="Lister", value="list"),
]


class TwitchNotifier(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
        twitch_notification_service: TwitchNotificationService,
        twitch_api_service: TwitchApiService | None,
    ) -> None:
        self.bot = bot
        self._service = twitch_notification_service
        self._twitch = twitch_api_service
        self._live_state: dict[tuple[int, str], bool] = {}

        if self._twitch is None:
            logger.warning("Twitch API credentials missing; notification loop disabled.")
        else:
            self.check_streams_task.start()
        logger.info("TwitchNotifier initialized.")

    def cog_unload(self) -> None:
        if self.check_streams_task.is_running():
            self.check_streams_task.cancel()

    @app_commands.command(name="streamer", description="Gerer les streamers Twitch a notifier.")
    @app_commands.describe(
        action="Action a effectuer",
        streamer="Nom du streamer Twitch pour add/remove",
    )
    @app_commands.choices(action=ACTION_CHOICES)
    @app_commands.default_permissions(administrator=True)
    async def streamer(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        streamer: Optional[str] = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("Cette commande doit etre executee dans un serveur.", ephemeral=True)
            return

        action_value = action.value.lower()
        if action_value in {"add", "remove"} and not streamer:
            await interaction.followup.send("Vous devez fournir le nom du streamer.", ephemeral=True)
            return

        if action_value == "add":
            result = await self._service.add_streamer(
                guild_id=interaction.guild.id,
                guild_name=interaction.guild.name,
                streamer=streamer or "",
            )
            await interaction.followup.send(_format_mutation_result(result.status, result.streamer_login), ephemeral=True)
            return

        if action_value == "remove":
            result = await self._service.remove_streamer(
                guild_id=interaction.guild.id,
                streamer=streamer or "",
            )
            await interaction.followup.send(_format_mutation_result(result.status, result.streamer_login), ephemeral=True)
            return

        if action_value == "list":
            streamers = await self._service.list_streamers(interaction.guild.id)
            await interaction.followup.send(format_streamer_list(streamers), ephemeral=True)
            return

        await interaction.followup.send("Action non reconnue.", ephemeral=True)

    @tasks.loop(minutes=1)
    async def check_streams_task(self) -> None:
        if self._twitch is None:
            return

        for guild in self.bot.guilds:
            try:
                await self._check_guild_streams(guild)
            except Exception:
                logger.exception("Twitch stream check failed for guild %s.", guild.id)

    @check_streams_task.before_loop
    async def before_check_streams(self) -> None:
        await self.bot.wait_until_ready()

    async def _check_guild_streams(self, guild: discord.Guild) -> None:
        channel_id = await self._service.get_notify_channel_id(guild.id)
        if channel_id is None:
            return

        streamers = await self._service.list_streamers(guild.id)
        if not streamers:
            return

        streams_resp = await self._twitch.get_streams_by_logins(streamers)
        live_now = {stream.user_login.lower(): stream for stream in streams_resp.data}

        users_resp = await self._twitch.get_users_by_logins(streamers)
        users = {user.login.lower(): user for user in users_resp.data}

        follower_counts: dict[str, int] = {}
        for login, user in users.items():
            try:
                follower_counts[login] = await self._twitch.get_followers_total(user.id)
            except Exception:
                logger.exception("Could not fetch follower count for %s.", login)
                follower_counts[login] = 0

        game_ids = list({stream.game_id for stream in live_now.values() if stream.game_id})
        game_images: dict[str, str] = {}
        if game_ids:
            games_resp = await self._twitch.get_games_by_ids(game_ids)
            game_images = {
                game.id: game.box_art_url.replace("{width}", "128").replace("{height}", "170")
                for game in games_resp.data
                if game.box_art_url
            }

        channel = self.bot.get_channel(channel_id)
        if not channel or not hasattr(channel, "send"):
            logger.warning("Configured Twitch channel %s not found for guild %s.", channel_id, guild.id)
            return

        for streamer_login in streamers:
            login = streamer_login.lower()
            key = (guild.id, login)
            was_live = self._live_state.get(key, False)
            is_live = login in live_now

            if is_live and not was_live:
                await self._send_live_notification(channel, login, live_now[login], users.get(login), follower_counts, game_images)

            self._live_state[key] = is_live

    async def _send_live_notification(
        self,
        channel,
        login: str,
        stream,
        user,
        follower_counts: dict[str, int],
        game_images: dict[str, str],
    ) -> None:
        thumbnail_url = None
        if stream.thumbnail_url:
            thumbnail_url = stream.thumbnail_url.replace("{width}", "640").replace("{height}", "360")

        stream_url = f"https://twitch.tv/{login}"
        notification = TwitchLiveNotification(
            streamer_login=user.display_name if user else login,
            title=stream.title or "Live Twitch",
            game_name=stream.game_name or "Inconnu",
            viewer_count=stream.viewer_count or 0,
            follower_count=follower_counts.get(login, 0),
            stream_url=stream_url,
            thumbnail_url=thumbnail_url,
            profile_image_url=user.profile_image_url if user else None,
            box_art_url=game_images.get(stream.game_id or ""),
            timestamp=datetime.now(timezone.utc),
        )
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Regarder le stream", url=stream_url, style=discord.ButtonStyle.link))
        await channel.send(embed=build_twitch_live_embed(notification), view=view)


def _format_mutation_result(status: str, streamer_login: str) -> str:
    if status == "created":
        return f"Streamer `{streamer_login}` ajoute."
    if status == "already_exists":
        return f"Streamer `{streamer_login}` deja configure."
    if status == "removed":
        return f"Streamer `{streamer_login}` supprime."
    if status == "not_found":
        return f"Streamer `{streamer_login}` introuvable."
    return "Nom de streamer invalide."


async def setup(bot: commands.Bot) -> None:
    twitch_notification_service = getattr(bot, "twitch_notification_service", None)
    if twitch_notification_service is None:
        logger.error("twitch_notification_service is not initialized. TwitchNotifier will not be loaded.")
        return

    twitch_api_service = getattr(bot, "twitch_api_service", None)
    await bot.add_cog(TwitchNotifier(bot, twitch_notification_service, twitch_api_service))
    logger.info("TwitchNotifier loaded.")
