import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from cogs.ranking.services.valorant_service import (
    get_featured_store,
    get_bundle_info,
    RateLimitException,
)
from cogs.shop.services.shop_service import (
    get_notify_channel_id,
    is_bundle_sent,
    mark_bundle_sent,
)

logger = logging.getLogger(__name__)

class ValorantShopNotifier(commands.Cog):
    """Notifie lorsqu'un nouveau shop Valorant est disponible, avec détails en thread."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
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
            logger.error(f"Erreur récupération shop: {exc}")
            return

        if not data:
            return

        for bundle in data:
            bundle_id = bundle.get("bundle_uuid")
            if not bundle_id:
                continue

            # Ne pas renvoyer un même bundle deux fois
            if await is_bundle_sent(bundle_id):
                continue

            # On marque tout de suite dans la base
            await mark_bundle_sent(bundle_id)

            # 1) Récupérer le méta-bundle pour l'embed principal
            try:
                info = await get_bundle_info(bundle_id)
            except RateLimitException:
                info = None
            except Exception as exc:
                logger.error(f"Erreur bundle info {bundle_id}: {exc}")
                info = None

            name       = info.get("displayName") if info else "Nouveau bundle"
            main_img   = info.get("displayIcon") if info else None
            expires_at = bundle.get("expires_at", "")
            try:
                dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                expires_str = dt.date().strftime("%d/%m/%Y")
            except Exception:
                expires_str = expires_at.split("T")[0]

            # 2) Créer l'embed principal
            embed = discord.Embed(
                title=f"🛍️ **{name}**",
                description="**Un nouveau bundle est dispo !** 🎉",
                color=discord.Color.red(),
            )
            embed.add_field(
                name="💰 Prix total",
                value=f"**{bundle.get('bundle_price', 0)} VP**",
                inline=True
            )
            if main_img:
                embed.set_image(url=main_img)
            embed.set_footer(text=f"⏳ Jusqu’au {expires_str}")

            # 3) Envoyer et créer le thread de détail
            for guild in self.bot.guilds:
                channel_id = await get_notify_channel_id(guild.id)
                if not channel_id:
                    continue
                channel = self.bot.get_channel(channel_id)
                if not channel:
                    continue

                try:
                    msg = await channel.send(embed=embed)
                    thread = await msg.create_thread(
                        name=f"Détails – {name}",
                        auto_archive_duration=1440
                    )

                    whole_sale_only = bundle.get("whole_sale_only", False)
                    items = bundle.get("items", [])

                    for entry in items:
                        item_name        = entry.get("name", "Item inconnu")
                        icon_url         = entry.get("image")
                        base_price       = entry.get("base_price")
                        discount_percent = entry.get("discount_percent", 0)

                        item_embed = discord.Embed(
                            title=item_name,
                            color=discord.Color.dark_gold()
                        )

                        if whole_sale_only:
                            item_embed.add_field(
                                name="⚠️ Vente groupée",
                                value="Disponible uniquement en bundle complet",
                                inline=False
                            )
                        else:
                            # Prix individuel
                            if base_price is not None:
                                item_embed.add_field(
                                    name="💰 Prix",
                                    value=f"**{base_price} VP**",
                                    inline=False
                                )
                            # Réduction seulement si > 0
                            if discount_percent > 0:
                                pct = int(discount_percent * 100)
                                reduction_str = "Gratuit" if pct >= 100 else f"-{pct}%"
                                item_embed.add_field(
                                    name="🏷 Réduction",
                                    value=f"**{reduction_str} dans le bundle**",
                                    inline=False
                                )

                        if icon_url:
                            # Image en grand
                            item_embed.set_image(url=icon_url)

                        await thread.send(embed=item_embed)

                except Exception as e:
                    logger.error(f"Erreur envoi bundle {bundle_id} guild {guild.id}: {e}")

    @check_shop_task.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(ValorantShopNotifier(bot))
    logger.info("ValorantShopNotifier chargé.")
