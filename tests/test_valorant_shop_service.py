from __future__ import annotations

import pytest

from cogs.shop.presenters import build_bundle_embed, thread_name_for_bundle
from cogs.shop.services import ShopBundle, ShopBundleItem, ShopBundleMetadata, ValorantShopService
from integrations.exceptions import ApiError
from integrations.henrikdev.models import StoreFeaturedResponse
from integrations.valorant_api.models import BundleResponseUuid


class FakeShopDb:
    def __init__(self) -> None:
        self.sent: set[tuple[int, str]] = set()

    async def is_bundle_sent(self, *, guild_id: int, bundle_uuid: str) -> bool:
        return (guild_id, bundle_uuid) in self.sent

    async def mark_bundle_sent(self, *, guild_id: int, guild_name: str | None, bundle_uuid: str) -> bool:
        key = (guild_id, bundle_uuid)
        if key in self.sent:
            return False
        self.sent.add(key)
        return True


class FakeChannels:
    async def get_one(self, guild_id: int, key: str) -> int | None:
        return 42 if key == "valorant_shop" else None


class FakeHenrik:
    is_configured = True

    async def get_featured_store(self):
        return (
            StoreFeaturedResponse.model_validate(
                {
                    "status": 200,
                    "data": [
                        {
                            "bundle_uuid": "bundle-1",
                            "seconds_remaining": 3600,
                            "bundle_price": 8700,
                            "whole_sale_only": False,
                            "expires_at": "2026-05-10T12:00:00Z",
                            "items": [
                                {
                                    "uuid": "item-1",
                                    "name": "Vandal Test",
                                    "image": "https://example.test/item.png",
                                    "type": "skin",
                                    "amount": 1,
                                    "discount_percent": 0,
                                    "base_price": 1775,
                                    "discounted_price": 1775,
                                    "promo_item": False,
                                }
                            ],
                        }
                    ],
                }
            ),
            None,
        )


class FakeValorantApi:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    async def get_bundle_by_uuid(self, bundle_uuid: str):
        if self.fail:
            raise ApiError("unavailable")
        return BundleResponseUuid.model_validate(
            {
                "status": 200,
                "data": {
                    "uuid": bundle_uuid,
                    "displayName": "Bundle Test",
                    "displayIcon": "https://example.test/icon.png",
                    "displayIcon2": None,
                    "verticalPromoImage": "https://example.test/vertical.png",
                },
            }
        )


def make_service(db: FakeShopDb | None = None, *, metadata_fail: bool = False) -> ValorantShopService:
    return ValorantShopService(
        db or FakeShopDb(),
        FakeChannels(),
        FakeHenrik(),
        FakeValorantApi(fail=metadata_fail),
    )


@pytest.mark.asyncio
async def test_valorant_shop_service_fetches_featured_bundles() -> None:
    bundles = await make_service().fetch_featured_bundles()

    assert len(bundles) == 1
    assert bundles[0].bundle_uuid == "bundle-1"
    assert bundles[0].items[0].name == "Vandal Test"


@pytest.mark.asyncio
async def test_valorant_shop_service_filters_and_marks_per_guild() -> None:
    db = FakeShopDb()
    service = make_service(db)
    bundles = await service.fetch_featured_bundles()

    assert await service.filter_new_bundles(guild_id=1, bundles=bundles) == bundles
    assert await service.mark_bundle_sent(guild_id=1, guild_name="Guild", bundle_uuid="bundle-1") is True
    assert await service.filter_new_bundles(guild_id=1, bundles=bundles) == ()
    assert await service.filter_new_bundles(guild_id=2, bundles=bundles) == bundles


@pytest.mark.asyncio
async def test_valorant_shop_service_reads_channel_config() -> None:
    assert await make_service().get_notify_channel_id(1) == 42


@pytest.mark.asyncio
async def test_valorant_shop_service_returns_none_when_metadata_fails() -> None:
    assert await make_service(metadata_fail=True).get_bundle_metadata("bundle-1") is None


def test_valorant_shop_presenter_builds_bundle_embed() -> None:
    bundle = ShopBundle(
        bundle_uuid="bundle-1",
        seconds_remaining=3600,
        bundle_price=8700,
        whole_sale_only=False,
        expires_at="2026-05-10T12:00:00Z",
        items=(
            ShopBundleItem(
                uuid="item-1",
                name="Vandal Test",
                image_url=None,
                item_type="skin",
                amount=1,
                discount_percent=0,
                base_price=1775,
                discounted_price=1775,
                promo_item=False,
            ),
        ),
    )
    metadata = ShopBundleMetadata(
        uuid="bundle-1",
        display_name="Bundle Test",
        display_icon_url=None,
        display_icon_2_url=None,
        vertical_promo_image_url="https://example.test/vertical.png",
    )

    embed = build_bundle_embed(bundle, metadata)

    assert embed.title == "Boutique Valorant - Bundle Test"
    assert embed.image.url == "https://example.test/vertical.png"
    assert thread_name_for_bundle(metadata, bundle) == "Details - Bundle Test"
