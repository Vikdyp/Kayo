from __future__ import annotations

import logging

import discord
from discord.ext import commands, tasks

from cogs.shop.presenters import (
    build_bundle_embed,
    build_item_embed,
    thread_name_for_bundle,
)
from cogs.shop.services import ShopBundle, ShopBundleMetadata, ValorantShopService
from integrations.exceptions import IntegrationError, RateLimitError

logger = logging.getLogger(__name__)


class ValorantShopNotifier(commands.Cog):
    def __init__(self, bot: commands.Bot, service: ValorantShopService) -> None:
        self.bot = bot
        self._service = service

        if not service.is_enabled:
            logger.warning("HENRIK_VALO_KEY missing; Valorant shop loop disabled.")
        else:
            self.check_shop_task.start()
        logger.info("ValorantShopNotifier initialized.")

    def cog_unload(self) -> None:
        if self.check_shop_task.is_running():
            self.check_shop_task.cancel()

    @tasks.loop(minutes=30)
    async def check_shop_task(self) -> None:
        try:
            bundles = await self._service.fetch_featured_bundles()
        except RateLimitError:
            logger.warning("Valorant shop check skipped: HenrikDev rate limit reached.")
            return
        except IntegrationError:
            logger.exception("Valorant shop check failed while fetching featured store.")
            return
        except Exception:
            logger.exception("Unexpected Valorant shop check failure.")
            return

        if not bundles:
            return

        metadata_cache: dict[str, ShopBundleMetadata | None] = {}
        for guild in self.bot.guilds:
            try:
                await self._notify_guild(guild, bundles, metadata_cache)
            except Exception:
                logger.exception("Valorant shop notification failed for guild %s.", guild.id)

    @check_shop_task.before_loop
    async def before_check_shop_task(self) -> None:
        await self.bot.wait_until_ready()

    async def _notify_guild(
        self,
        guild: discord.Guild,
        bundles: tuple[ShopBundle, ...],
        metadata_cache: dict[str, ShopBundleMetadata | None],
    ) -> None:
        channel_id = await self._service.get_notify_channel_id(guild.id)
        if channel_id is None:
            return

        channel = self.bot.get_channel(channel_id)
        if channel is None or not hasattr(channel, "send"):
            logger.warning("Configured Valorant shop channel %s not found for guild %s.", channel_id, guild.id)
            return

        new_bundles = await self._service.filter_new_bundles(guild_id=guild.id, bundles=bundles)
        for bundle in new_bundles:
            metadata = await self._get_metadata(bundle.bundle_uuid, metadata_cache)
            await self._send_bundle_notification(channel, bundle, metadata)
            await self._service.mark_bundle_sent(
                guild_id=guild.id,
                guild_name=guild.name,
                bundle_uuid=bundle.bundle_uuid,
            )

    async def _get_metadata(
        self,
        bundle_uuid: str,
        metadata_cache: dict[str, ShopBundleMetadata | None],
    ) -> ShopBundleMetadata | None:
        if bundle_uuid not in metadata_cache:
            metadata_cache[bundle_uuid] = await self._service.get_bundle_metadata(bundle_uuid)
        return metadata_cache[bundle_uuid]

    async def _send_bundle_notification(
        self,
        channel,
        bundle: ShopBundle,
        metadata: ShopBundleMetadata | None,
    ) -> None:
        message = await channel.send(embed=build_bundle_embed(bundle, metadata))
        if not bundle.items:
            return

        try:
            thread = await message.create_thread(
                name=thread_name_for_bundle(metadata, bundle),
                auto_archive_duration=1440,
            )
        except (discord.Forbidden, discord.HTTPException):
            logger.exception("Could not create Valorant shop details thread for bundle %s.", bundle.bundle_uuid)
            return

        for item in bundle.items:
            try:
                await thread.send(embed=build_item_embed(item, whole_sale_only=bundle.whole_sale_only))
            except (discord.Forbidden, discord.HTTPException):
                logger.exception("Could not send Valorant shop item %s.", item.uuid)


async def setup(bot: commands.Bot) -> None:
    service = getattr(bot, "valorant_shop_service", None)
    if service is None:
        logger.error("valorant_shop_service is not initialized. ValorantShopNotifier will not be loaded.")
        return

    await bot.add_cog(ValorantShopNotifier(bot, service))
    logger.info("ValorantShopNotifier loaded.")
