import os
import logging
from datetime import datetime, timezone
from typing import Dict, Tuple, Optional

import discord
from discord import app_commands, Embed, ui, ButtonStyle
from discord.ext import commands, tasks

from cogs.twitch.service.twitch_service import StreamerService
from integrations.http_client import HTTPClient
from integrations.twitch.service import TwitchService

logger = logging.getLogger(__name__)


def abbreviate_number(n: int) -> str:
    if n >= 1_000_000:
        val = n / 1_000_000
        if val.is_integer():
            return f"{int(val)}m"
        return f"{val:.1f}m"
    if n >= 10_000:
        val = n // 1_000
        return f"{val}k"
    return str(n)


class TwitchNotifier(commands.Cog):
    """
    Cog pour surveiller l'état des lives Twitch de streamers partenaires
    et poster une notification riche dans le salon configuré.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.live_state: Dict[Tuple[int, str], bool] = {}

        self._http: HTTPClient | None = None
        self._twitch: TwitchService | None = None

        self.check_streams_task.start()
        logger.info("Twitch ID     : %s", os.getenv("TWITCH_CLIENT_ID"))
        logger.info("Twitch Secret : %s", "OK" if os.getenv("TWITCH_CLIENT_SECRET") else "MANQUANT")

    def cog_unload(self):
        self.check_streams_task.cancel()
        # on ferme la session HTTP proprement
        if self._http is not None:
            # pas await ici; on schedule
            try:
                self.bot.loop.create_task(self._http.__aexit__(None, None, None))
            except Exception:
                pass

    @app_commands.command(name="streamer", description="Gérer les streamers à notifier (add/remove/list)")
    @app_commands.describe(action="add / remove / list", streamer="Nom du streamer Twitch (requis pour add/remove)")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Ajouter", value="add"),
            app_commands.Choice(name="Supprimer", value="remove"),
            app_commands.Choice(name="Lister", value="list"),
        ]
    )
    @app_commands.default_permissions(administrator=True)
    async def streamer(self, interaction: discord.Interaction, action: app_commands.Choice[str], streamer: str = None):
        await interaction.response.defer(ephemeral=True)
        act = action.value
        gid = interaction.guild.id

        if act in ("add", "remove") and not streamer:
            return await interaction.followup.send("🚫 Vous devez fournir le nom du streamer.", ephemeral=True)

        if act == "add":
            ok = await StreamerService.add_streamer(gid, streamer)
            msg = f"✅ Streamer `{streamer}` ajouté." if ok else f"❌ Échec de l'ajout de `{streamer}`."
        elif act == "remove":
            ok = await StreamerService.remove_streamer(gid, streamer)
            msg = f"✅ Streamer `{streamer}` supprimé." if ok else f"❌ Échec de la suppression de `{streamer}`."
        else:
            lst = await StreamerService.list_streamers(gid)
            msg = "📜 Aucun streamer configuré." if not lst else "📜 Streamers : " + ", ".join(f"`{s}`" for s in lst)

        await interaction.followup.send(msg, ephemeral=True)

    @tasks.loop(minutes=1)
    async def check_streams_task(self):
        if self._twitch is None:
            # sécurité: si before_loop n’a pas encore initialisé
            return

        now = datetime.now(timezone.utc)

        for guild in self.bot.guilds:
            channel_id = await StreamerService.get_notify_channel_id(guild.id)
            if not channel_id:
                continue

            streamers = await StreamerService.list_streamers(guild.id)
            if not streamers:
                continue

            # 1) streams live
            streams_resp = await self._twitch.get_streams_by_logins(streamers)
            live_now = {s.user_login: s for s in streams_resp.data}

            # 2) users (avatar + id)
            users_resp = await self._twitch.get_users_by_logins(streamers)
            users = {u.login: u for u in users_resp.data}

            # 3) followers (un par streamer)
            follower_counts: Dict[str, int] = {}
            for login, user in users.items():
                try:
                    follower_counts[login] = await self._twitch.get_followers_total(user.id)
                except Exception:
                    follower_counts[login] = 0

            # 4) games (box art)
            game_ids = list({s.game_id for s in live_now.values() if s.game_id})
            game_images: Dict[str, str] = {}
            if game_ids:
                games_resp = await self._twitch.get_games_by_ids(game_ids)
                for g in games_resp.data:
                    if g.box_art_url:
                        game_images[g.id] = g.box_art_url.replace("{width}", "128").replace("{height}", "170")

            channel = self.bot.get_channel(channel_id)
            if not channel:
                continue

            for name in streamers:
                key = (guild.id, name)
                was_live = self.live_state.get(key, False)
                # Twitch renvoie les login en lowercase -> normaliser
                login = name.lower()
                is_live = login in live_now

                if is_live and not was_live:
                    info = live_now[login]
                    user_info = users.get(login)

                    title = info.title or "Live Twitch"
                    game_name = info.game_name or "Inconnu"
                    viewers = info.viewer_count or 0
                    game_id = info.game_id or ""

                    embed = Embed(
                        title=f"{name} est en live !",
                        url=f"https://twitch.tv/{name}",
                        description=f"**{title}**",
                        color=discord.Color.purple(),
                    )

                    profile_url: Optional[str] = user_info.profile_image_url if user_info else None
                    if profile_url:
                        embed.set_author(name=name, icon_url=profile_url, url=f"https://twitch.tv/{name}")

                    thumb = info.thumbnail_url
                    if thumb:
                        embed.set_image(url=thumb.format(width=640, height=360))

                    box_art = game_images.get(game_id)
                    embed.set_thumbnail(url=box_art or profile_url)

                    embed.add_field(name="📺 Catégorie", value=game_name, inline=True)
                    followers = follower_counts.get(login, 0)
                    embed.add_field(name="👥 Followers", value=abbreviate_number(followers), inline=True)
                    embed.add_field(name="👀 Viewers", value=abbreviate_number(viewers), inline=True)

                    embed.timestamp = now

                    view = ui.View()
                    view.add_item(
                        ui.Button(label="▶️ Regarder le stream", url=f"https://twitch.tv/{name}", style=ButtonStyle.link)
                    )

                    sent = await channel.send(embed=embed, view=view)
                    try:
                        await sent.add_reaction("🔥")
                    except Exception:
                        logger.warning("Impossible d'ajouter la réaction 🔥 pour %s", name)

                self.live_state[key] = is_live

    @check_streams_task.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

        client_id = os.getenv("TWITCH_CLIENT_ID")
        client_secret = os.getenv("TWITCH_CLIENT_SECRET")
        if not client_id or not client_secret:
            logger.error("TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET non définis.")
            return

        # Initialise une session HTTP unique réutilisée par TwitchService
        self._http = HTTPClient()
        await self._http.__aenter__()
        self._twitch = TwitchService(self._http, client_id=client_id, client_secret=client_secret)


async def setup(bot: commands.Bot):
    await bot.add_cog(TwitchNotifier(bot))
    logger.info("TwitchNotifier Cog chargé.")
