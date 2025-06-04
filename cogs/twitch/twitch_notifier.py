# cogs/twitch/twitch_notifier.py

import os
import logging
import aiohttp
from datetime import datetime, timezone
from typing import Dict, Tuple, Optional

import discord
from discord import app_commands, Embed, ui, ButtonStyle
from discord.ext import commands, tasks

from cogs.twitch.service.twitch_service import StreamerService

logger = logging.getLogger(__name__)


def abbreviate_number(n: int) -> str:
    """Abbreviate number: >=1e6 as Xm or Xm.Ym, >=1e4 as Xk, else raw."""
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
        # (guild_id, streamer_name) -> bool (état live précédent)
        self.live_state: Dict[Tuple[int, str], bool] = {}
        self.check_streams_task.start()
        logger.info(f"Twitch ID     : {os.getenv('TWITCH_CLIENT_ID')}")
        logger.info(f"Twitch Secret : {'OK' if os.getenv('TWITCH_CLIENT_SECRET') else 'MANQUANT'}")

    def cog_unload(self):
        self.check_streams_task.cancel()

    @app_commands.command(
        name="streamer",
        description="Gérer les streamers à notifier (add/remove/list)"
    )
    @app_commands.describe(
        action="add / remove / list",
        streamer="Nom du streamer Twitch (requis pour add/remove)"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Ajouter", value="add"),
        app_commands.Choice(name="Supprimer", value="remove"),
        app_commands.Choice(name="Lister",   value="list"),
    ])
    @app_commands.default_permissions(administrator=True)
    async def streamer(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        streamer: str = None
    ):
        await interaction.response.defer(ephemeral=True)
        act = action.value
        gid = interaction.guild.id

        if act in ("add", "remove") and not streamer:
            return await interaction.followup.send(
                "🚫 Vous devez fournir le nom du streamer.", ephemeral=True
            )

        if act == "add":
            ok = await StreamerService.add_streamer(gid, streamer)
            msg = f"✅ Streamer `{streamer}` ajouté." if ok else f"❌ Échec de l'ajout de `{streamer}`."
        elif act == "remove":
            ok = await StreamerService.remove_streamer(gid, streamer)
            msg = f"✅ Streamer `{streamer}` supprimé." if ok else f"❌ Échec de la suppression de `{streamer}`."
        else:
            lst = await StreamerService.list_streamers(gid)
            if not lst:
                msg = "📜 Aucun streamer configuré."
            else:
                msg = "📜 Streamers : " + ", ".join(f"`{s}`" for s in lst)

        await interaction.followup.send(msg, ephemeral=True)

    @tasks.loop(minutes=1)
    async def check_streams_task(self):
        client_id = os.getenv("TWITCH_CLIENT_ID")
        client_secret = os.getenv("TWITCH_CLIENT_SECRET")
        if not client_id or not client_secret:
            logger.error("TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET non définis.")
            return

        async with aiohttp.ClientSession() as session:
            # 1. récupère un token OAuth App
            token_resp = await session.post(
                "https://id.twitch.tv/oauth2/token",
                params={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "grant_type": "client_credentials"
                }
            )
            token_data = await token_resp.json()
            oauth_token = token_data.get("access_token")
            if not oauth_token:
                logger.error(f"Twitch OAuth error: {token_data}")
                return

            headers = {
                "Client-ID": client_id,
                "Authorization": f"Bearer {oauth_token}"
            }

            now = datetime.now(timezone.utc)

            for guild in self.bot.guilds:
                channel_id = await StreamerService.get_notify_channel_id(guild.id)
                if not channel_id:
                    continue

                streamers = await StreamerService.list_streamers(guild.id)
                if not streamers:
                    continue

                # 2. interroger Helix /streams
                params_streams = [("user_login", name) for name in streamers]
                async with session.get(
                    "https://api.twitch.tv/helix/streams",
                    params=params_streams,
                    headers=headers
                ) as resp:
                    data = await resp.json()
                    live_now = {d["user_login"]: d for d in data.get("data", [])}

                # 3. interroger Helix /users pour avatars
                params_users = [("login", name) for name in streamers]
                async with session.get(
                    "https://api.twitch.tv/helix/users",
                    params=params_users,
                    headers=headers
                ) as uresp:
                    udata = await uresp.json()
                    users = {u["login"]: u for u in udata.get("data", [])}

                # 4. récupérer le nombre de followers via Helix /channels/followers
                follower_counts: Dict[str, int] = {}
                for name, user in users.items():
                    user_id = user.get("id")
                    if not user_id:
                        continue
                    async with session.get(
                        "https://api.twitch.tv/helix/channels/followers",
                        params={"broadcaster_id": user_id, "first": 1},
                        headers=headers
                    ) as fresp:
                        fdata = await fresp.json()
                        follower_counts[name] = fdata.get("total", 0)

                # 5. interroger Helix /games pour box_art_url
                game_ids = list({info.get("game_id") for info in live_now.values() if info.get("game_id")})
                game_images: Dict[str, str] = {}
                if game_ids:
                    params_games = [("id", gid) for gid in game_ids]
                    async with session.get(
                        "https://api.twitch.tv/helix/games",
                        params=params_games,
                        headers=headers
                    ) as gres:
                        gdata = await gres.json()
                        for g in gdata.get("data", []):
                            game_images[g["id"]] = g["box_art_url"].replace("{width}", "128").replace("{height}", "170")

                channel = self.bot.get_channel(channel_id)
                if not channel:
                    continue

                for name in streamers:
                    key = (guild.id, name)
                    was_live = self.live_state.get(key, False)
                    is_live = name in live_now

                    if is_live and not was_live:
                        info = live_now[name]
                        user_info = users.get(name, {})

                        title = info.get("title") or "Live Twitch"
                        game_name = info.get("game_name") or "Inconnu"
                        viewers = info.get("viewer_count", 0)
                        game_id = info.get("game_id", "")

                        embed = Embed(
                            title=f"{name} est en live !",
                            url=f"https://twitch.tv/{name}",
                            description=f"**{title}**",
                            color=discord.Color.purple()
                        )
                        # Auteur + avatar
                        profile_url: Optional[str] = user_info.get("profile_image_url")
                        if profile_url:
                            embed.set_author(name=name, icon_url=profile_url, url=f"https://twitch.tv/{name}")

                        # Aperçu du stream en grand
                        thumb = info.get("thumbnail_url")
                        if thumb:
                            embed.set_image(url=thumb.format(width=640, height=360))

                        # Thumbnail du jeu ou de l’avatar
                        box_art = game_images.get(game_id)
                        embed.set_thumbnail(url=box_art or profile_url)

                        # Champs d’infos
                        embed.add_field(name="📺 Catégorie", value=game_name, inline=True)
                        followers = follower_counts.get(name, 0)
                        embed.add_field(name="👥 Followers", value=abbreviate_number(followers), inline=True)

                        # Timestamp natif pour affichage relatif
                        embed.timestamp = now

                        # Bouton « Regarder »
                        view = ui.View()
                        view.add_item(ui.Button(
                            label="▶️ Regarder le stream",
                            url=f"https://twitch.tv/{name}",
                            style=ButtonStyle.link
                        ))

                        sent = await channel.send(embed=embed, view=view)
                        # Ajouter des réactions automatiques
                        for emoji in ('🔥'):
                            try:
                                await sent.add_reaction(emoji)
                            except Exception:
                                logger.warning(f"Impossible d'ajouter la réaction {emoji} pour {name}")

                    # mise à jour de l’état
                    self.live_state[key] = is_live

    @check_streams_task.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(TwitchNotifier(bot))
    logger.info("TwitchNotifier Cog chargé.")
