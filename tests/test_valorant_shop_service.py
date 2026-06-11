from __future__ import annotations

import pytest

from cogs.shop import shop_notifier
from cogs.shop.shop_notifier import ValorantShopNotifier
from cogs.shop.presenters import build_bundle_embed, build_item_embed, thread_name_for_bundle
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


class FakeGuild:
    id = 1
    name = "Guild"


class FakeThread:
    def __init__(self) -> None:
        self.embeds = []

    async def send(self, *, embed) -> None:
        self.embeds.append(embed)


class FakeMessage:
    def __init__(self) -> None:
        self.thread = FakeThread()
        self.thread_name: str | None = None
        self.auto_archive_duration: int | None = None

    async def create_thread(self, *, name: str, auto_archive_duration: int) -> FakeThread:
        self.thread_name = name
        self.auto_archive_duration = auto_archive_duration
        return self.thread


class FakeShopChannel:
    def __init__(self, *, fail_send: bool = False) -> None:
        self.fail_send = fail_send
        self.sent_embeds = []
        self.messages: list[FakeMessage] = []

    async def send(self, *, embed) -> FakeMessage:
        if self.fail_send:
            raise RuntimeError("send failed")
        self.sent_embeds.append(embed)
        message = FakeMessage()
        self.messages.append(message)
        return message


class FakeBot:
    guilds = [FakeGuild()]

    def __init__(self, channel: FakeShopChannel) -> None:
        self.channel = channel

    def get_channel(self, channel_id: int):
        return self.channel if channel_id == 42 else None


class FakeFlakyFeaturedStoreService:
    def __init__(self) -> None:
        self.calls = 0

    async def fetch_featured_bundles(self):
        self.calls += 1
        if self.calls == 1:
            raise ApiError("HTTP 502: Bad Gateway")
        return ("bundle",)


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

    assert embed.title == "🛍️ Bundle Test"
    assert embed.description == "Un nouveau bundle est dispo ! 🎉"
    assert embed.fields[0].name == "💰 Prix total"
    assert embed.fields[0].value == "8700 VP"
    assert embed.fields[1].name == "🛍️ **Bundle Test**"
    assert embed.fields[1].value == "⏳ Jusqu’au 10/05/2026"
    assert embed.image.url == "https://example.test/vertical.png"
    assert embed.footer.text is None
    assert thread_name_for_bundle(metadata, bundle) == "🛍️ Bundle Test"


def test_valorant_shop_presenter_builds_item_embed_like_legacy_message() -> None:
    item = ShopBundleItem(
        uuid="item-1",
        name="Blackthorn Buddy",
        image_url="https://example.test/item.png",
        item_type="buddy",
        amount=1,
        discount_percent=100,
        base_price=475,
        discounted_price=0,
        promo_item=False,
    )

    embed = build_item_embed(item, whole_sale_only=True)

    assert embed.title == "Blackthorn Buddy"
    assert [(field.name, field.value) for field in embed.fields] == [
        ("💰 Prix", "475 VP"),
        ("🏷 Réduction", "Gratuit dans le bundle"),
    ]
    assert embed.image.url == "https://example.test/item.png"


def test_shop_notifier_checks_shop_every_five_minutes() -> None:
    assert ValorantShopNotifier.check_shop_task.minutes == 5.0


@pytest.mark.asyncio
async def test_shop_notifier_retries_transient_featured_store_errors(monkeypatch) -> None:
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(shop_notifier.asyncio, "sleep", fake_sleep)
    service = FakeFlakyFeaturedStoreService()
    notifier = ValorantShopNotifier.__new__(ValorantShopNotifier)
    notifier._service = service

    bundles = await notifier._fetch_featured_bundles_with_retry(retry_delays=(0.0,))

    assert bundles == ("bundle",)
    assert service.calls == 2
    assert sleeps == [0.0]


@pytest.mark.asyncio
async def test_shop_notifier_sends_bundle_thread_and_marks_sent() -> None:
    db = FakeShopDb()
    service = make_service(db)
    channel = FakeShopChannel()
    notifier = ValorantShopNotifier.__new__(ValorantShopNotifier)
    notifier.bot = FakeBot(channel)
    notifier._service = service
    bundles = await service.fetch_featured_bundles()

    await notifier._notify_guild(FakeGuild(), bundles, {})

    assert len(channel.sent_embeds) == 1
    assert channel.sent_embeds[0].title == "🛍️ Bundle Test"
    assert channel.messages[0].thread_name == "🛍️ Bundle Test"
    assert channel.messages[0].auto_archive_duration == 1440
    assert [embed.title for embed in channel.messages[0].thread.embeds] == ["Vandal Test"]
    assert (1, "bundle-1") in db.sent


@pytest.mark.asyncio
async def test_shop_notifier_does_not_mark_sent_when_main_message_fails() -> None:
    db = FakeShopDb()
    service = make_service(db)
    channel = FakeShopChannel(fail_send=True)
    notifier = ValorantShopNotifier.__new__(ValorantShopNotifier)
    notifier.bot = FakeBot(channel)
    notifier._service = service
    bundles = await service.fetch_featured_bundles()

    with pytest.raises(RuntimeError, match="send failed"):
        await notifier._notify_guild(FakeGuild(), bundles, {})

    assert db.sent == set()
