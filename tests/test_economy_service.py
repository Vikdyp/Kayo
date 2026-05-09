from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from cogs.economy.services import EconomyService


class FakeEconomyDbService:
    def __init__(self) -> None:
        self.claim_kwargs = None
        self.buy_kwargs = None
        self.transfer_kwargs = None

    async def claim_daily(self, **kwargs):
        self.claim_kwargs = kwargs
        return SimpleNamespace(claimed=True, amount=kwargs["amount"], balance=kwargs["amount"], last_daily_claim=kwargs["claim_date"])

    async def buy_item(self, **kwargs):
        self.buy_kwargs = kwargs
        return SimpleNamespace(purchased=True, balance=50, item_name=kwargs["item_name"])

    async def transfer_item(self, **kwargs):
        self.transfer_kwargs = kwargs
        return SimpleNamespace(transferred=True, item_name=kwargs["item_name"])


def test_economy_daily_amount_uses_role_bonuses() -> None:
    service = EconomyService(FakeEconomyDbService())

    assert service.calculate_daily_amount([]) == 100
    assert service.calculate_daily_amount(["bon joueur"]) == 200
    assert service.calculate_daily_amount(["booster"]) == 125
    assert service.calculate_daily_amount(["bon joueur", "booster"]) == 250


def test_economy_generate_shop_uses_item_pool() -> None:
    service = EconomyService(FakeEconomyDbService(), item_pool=("A",))

    items = service.generate_shop(count=3)

    assert [item.name for item in items] == ["A", "A", "A"]
    assert all(100 <= item.price <= 500 for item in items)


@pytest.mark.asyncio
async def test_economy_claim_daily_delegates_calculated_amount() -> None:
    db = FakeEconomyDbService()
    service = EconomyService(db)

    result = await service.claim_daily(
        guild_id=1,
        guild_name="Guild",
        discord_user_id=2,
        role_names=["bon joueur"],
        claim_date=date(2026, 5, 9),
    )

    assert result.amount == 200
    assert db.claim_kwargs["amount"] == 200
    assert db.claim_kwargs["guild_id"] == 1
    assert db.claim_kwargs["discord_user_id"] == 2
