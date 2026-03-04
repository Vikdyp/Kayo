# cogs/shop/services/shop_service.py

from __future__ import annotations

import logging
from typing import Optional

from cogs.configuration.services.channel_service import ChannelConfigurationService
from database.services.valorant_sent_bundles_service import ValorantSentBundlesService

logger = logging.getLogger(__name__)

CHANNEL_KEY = "valorant_shop"


class ShopService:
    """Service métier pour les notifications de boutique Valorant."""

    def __init__(
        self,
        bundles_svc: ValorantSentBundlesService,
        channel_config_svc: ChannelConfigurationService,
    ):
        self._bundles_svc = bundles_svc
        self._channel_svc = channel_config_svc

    async def get_notify_channel_id(self, guild_id: int) -> Optional[int]:
        return await self._channel_svc.get_one(guild_id, CHANNEL_KEY)

    async def is_bundle_sent(self, bundle_uuid: str) -> bool:
        return await self._bundles_svc.is_sent(bundle_uuid)

    async def mark_bundle_sent(self, bundle_uuid: str) -> None:
        await self._bundles_svc.mark_sent(bundle_uuid)
