import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from cogs.ranking.services.valorant_service import (
    get_featured_store,
    get_bundle_info,
    RateLimitException,
)
from cogs.valorant.services.shop_service import get_notify_channel_id

logger = logging.getLogger(__name__)

class ValorantShopNotifier(commands.Cog):
    """Notifie lorsqu'un nouveau shop Valorant est disponible."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.current_bundle_id: str | None = None
        self.check_shop_task.start()

    def cog_unload(self):
        self.check_shop_task.cancel()

    @tasks.loop(minutes=30)
    async def check_shop_task(self):
        try:
            data = await get_featured_store()
        except RateLimitException:
            return
        except Exception as exc:
            logger.error(f"Erreur lors de la récupération du shop: {exc}")
            return

        if not data:
            return

        bundle = data[0]
        bundle_id = bundle.get("bundle_uuid")
        if not bundle_id or bundle_id == self.current_bundle_id:
            return

        self.current_bundle_id = bundle_id

        try:
            info = await get_bundle_info(bundle_id)
        except RateLimitException:
            info = None
        except Exception as exc:
            logger.error(f"Erreur bundle info {bundle_id}: {exc}")
            info = None

        name = info.get("displayName") if info else "Nouveau bundle"
        image = info.get("displayIcon") if info else None
        expires = bundle.get("expires_at")
        price = bundle.get("bundle_price", 0)

        embed = discord.Embed(
            title=name,
            description=f"Expire le {expires}",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Prix", value=f"{price}")
        if image:
            embed.set_thumbnail(url=image)

        for guild in self.bot.guilds:
            channel_id = await get_notify_channel_id(guild.id)
            if not channel_id:
                continue
            channel = self.bot.get_channel(channel_id)
            if channel:
                try:
                    await channel.send(embed=embed)
                except Exception as e:
                    logger.error(f"Envoi impossible dans {channel_id}: {e}")

    @check_shop_task.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(ValorantShopNotifier(bot))
    logger.info("ValorantShopNotifier chargé.")

