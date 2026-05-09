from __future__ import annotations

from dataclasses import dataclass

from database.services.guild_channels_service import ChannelConfigurationService
from database.services.valorant_shop_service import ValorantShopDbService
from integrations.exceptions import IntegrationError
from integrations.henrikdev.service import HenrikDevService
from integrations.valorant_api.service import ValorantApiService

SHOP_CHANNEL_KEY = "valorant_shop"


@dataclass(frozen=True, slots=True)
class ShopBundleItem:
    uuid: str
    name: str
    image_url: str | None
    item_type: str | None
    amount: int | None
    discount_percent: float
    base_price: int | None
    discounted_price: int | None
    promo_item: bool


@dataclass(frozen=True, slots=True)
class ShopBundle:
    bundle_uuid: str
    seconds_remaining: int | None
    bundle_price: int
    whole_sale_only: bool
    expires_at: str | None
    items: tuple[ShopBundleItem, ...]


@dataclass(frozen=True, slots=True)
class ShopBundleMetadata:
    uuid: str
    display_name: str
    display_icon_url: str | None
    display_icon_2_url: str | None
    vertical_promo_image_url: str | None


class ValorantShopService:
    def __init__(
        self,
        shop_db_service: ValorantShopDbService,
        channel_config_service: ChannelConfigurationService,
        henrik_service: HenrikDevService,
        valorant_api_service: ValorantApiService,
    ) -> None:
        self._shop_db = shop_db_service
        self._channels = channel_config_service
        self._henrik = henrik_service
        self._valorant_api = valorant_api_service

    @property
    def is_enabled(self) -> bool:
        return bool(getattr(self._henrik, "is_configured", True))

    async def get_notify_channel_id(self, guild_id: int) -> int | None:
        return await self._channels.get_one(guild_id, SHOP_CHANNEL_KEY)

    async def fetch_featured_bundles(self) -> tuple[ShopBundle, ...]:
        response, _ = await self._henrik.get_featured_store()
        return tuple(_bundle_from_model(bundle) for bundle in response.data)

    async def get_bundle_metadata(self, bundle_uuid: str) -> ShopBundleMetadata | None:
        try:
            response = await self._valorant_api.get_bundle_by_uuid(bundle_uuid)
        except IntegrationError:
            return None

        return ShopBundleMetadata(
            uuid=response.data.uuid,
            display_name=response.data.displayName,
            display_icon_url=response.data.displayIcon,
            display_icon_2_url=response.data.displayIcon2,
            vertical_promo_image_url=response.data.verticalPromoImage,
        )

    async def is_bundle_sent(self, *, guild_id: int, bundle_uuid: str) -> bool:
        return await self._shop_db.is_bundle_sent(guild_id=guild_id, bundle_uuid=bundle_uuid)

    async def mark_bundle_sent(
        self,
        *,
        guild_id: int,
        guild_name: str | None,
        bundle_uuid: str,
    ) -> bool:
        return await self._shop_db.mark_bundle_sent(
            guild_id=guild_id,
            guild_name=guild_name,
            bundle_uuid=bundle_uuid,
        )

    async def filter_new_bundles(
        self,
        *,
        guild_id: int,
        bundles: tuple[ShopBundle, ...],
    ) -> tuple[ShopBundle, ...]:
        new_bundles: list[ShopBundle] = []
        for bundle in bundles:
            if not await self.is_bundle_sent(guild_id=guild_id, bundle_uuid=bundle.bundle_uuid):
                new_bundles.append(bundle)
        return tuple(new_bundles)


def _bundle_from_model(bundle) -> ShopBundle:
    return ShopBundle(
        bundle_uuid=bundle.bundle_uuid,
        seconds_remaining=bundle.seconds_remaining,
        bundle_price=bundle.bundle_price,
        whole_sale_only=bundle.whole_sale_only,
        expires_at=bundle.expires_at,
        items=tuple(
            ShopBundleItem(
                uuid=item.uuid,
                name=item.name,
                image_url=item.image,
                item_type=item.type,
                amount=item.amount,
                discount_percent=item.discount_percent,
                base_price=item.base_price,
                discounted_price=item.discounted_price,
                promo_item=item.promo_item,
            )
            for item in bundle.items
        ),
    )
