from __future__ import annotations

import random
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from database.services.economy_service import (
    DailyClaimInfo,
    EconomyDbService,
    PurchaseInfo,
    TransferInfo,
)

DEFAULT_SHOP_ITEMS = (
    "Skin Rouge",
    "Skin Bleu",
    "Skin Vert",
    "Skin Jaune",
    "Skin Epique",
    "Skin Legendaire",
)


@dataclass(frozen=True, slots=True)
class DailyShopItem:
    name: str
    price: int


class EconomyService:
    def __init__(
        self,
        economy_db_service: EconomyDbService,
        *,
        item_pool: Sequence[str] = DEFAULT_SHOP_ITEMS,
    ) -> None:
        self._economy = economy_db_service
        self._item_pool = tuple(item_pool)

    def generate_shop(self, *, count: int = 4) -> tuple[DailyShopItem, ...]:
        return tuple(
            DailyShopItem(
                name=random.choice(self._item_pool),
                price=random.randint(100, 500),
            )
            for _ in range(count)
        )

    def calculate_daily_amount(self, role_names: Iterable[str]) -> int:
        names = {role_name.casefold() for role_name in role_names}
        amount = 200 if "bon joueur" in names else 100
        if "booster" in names:
            amount = int(amount * 1.25)
        return amount

    async def claim_daily(
        self,
        *,
        guild_id: int,
        guild_name: str | None,
        discord_user_id: int,
        role_names: Iterable[str],
        claim_date: date,
    ) -> DailyClaimInfo:
        amount = self.calculate_daily_amount(role_names)
        return await self._economy.claim_daily(
            guild_id=guild_id,
            guild_name=guild_name,
            discord_user_id=discord_user_id,
            amount=amount,
            claim_date=claim_date,
        )

    async def buy_item(
        self,
        *,
        guild_id: int,
        guild_name: str | None,
        discord_user_id: int,
        item: DailyShopItem,
    ) -> PurchaseInfo:
        return await self._economy.buy_item(
            guild_id=guild_id,
            guild_name=guild_name,
            discord_user_id=discord_user_id,
            item_name=item.name,
            price=item.price,
        )

    async def list_inventory(self, *, guild_id: int, guild_name: str | None, discord_user_id: int):
        return await self._economy.list_inventory(
            guild_id=guild_id,
            guild_name=guild_name,
            discord_user_id=discord_user_id,
        )

    async def transfer_item(
        self,
        *,
        guild_id: int,
        guild_name: str | None,
        from_discord_user_id: int,
        to_discord_user_id: int,
        item_name: str,
    ) -> TransferInfo:
        return await self._economy.transfer_item(
            guild_id=guild_id,
            guild_name=guild_name,
            from_discord_user_id=from_discord_user_id,
            to_discord_user_id=to_discord_user_id,
            item_name=item_name,
        )
