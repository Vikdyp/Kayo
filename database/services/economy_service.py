from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from database.repos.economy_inventory_repo import EconomyInventoryRepo
from database.repos.economy_profiles_repo import EconomyProfilesRepo
from database.repos.guilds_repo import GuildsRepo
from database.repos.user_repo import UserRepo


@dataclass(frozen=True, slots=True)
class EconomyProfileInfo:
    guild_id: int
    discord_user_id: int
    balance: int
    last_daily_claim: Optional[date]


@dataclass(frozen=True, slots=True)
class EconomyInventoryItemInfo:
    item_name: str
    quantity: int


@dataclass(frozen=True, slots=True)
class DailyClaimInfo:
    claimed: bool
    amount: int
    balance: int
    last_daily_claim: Optional[date]


@dataclass(frozen=True, slots=True)
class PurchaseInfo:
    purchased: bool
    balance: int
    item_name: str


@dataclass(frozen=True, slots=True)
class TransferInfo:
    transferred: bool
    item_name: str


class EconomyDbService:
    def __init__(self, db) -> None:
        self._db = db

    async def get_profile(
        self,
        *,
        guild_id: int,
        guild_name: str | None,
        discord_user_id: int,
    ) -> EconomyProfileInfo:
        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            user_id = await UserRepo.ensure_exists(conn, discord_id=discord_user_id)
            row = await EconomyProfilesRepo.ensure_exists(conn, guild_id=guild_id, user_id=user_id)
            return EconomyProfileInfo(
                guild_id=row.guild_id,
                discord_user_id=discord_user_id,
                balance=row.balance,
                last_daily_claim=row.last_daily_claim,
            )

    async def claim_daily(
        self,
        *,
        guild_id: int,
        guild_name: str | None,
        discord_user_id: int,
        amount: int,
        claim_date: date,
    ) -> DailyClaimInfo:
        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            user_id = await UserRepo.ensure_exists(conn, discord_id=discord_user_id)
            profile = await EconomyProfilesRepo.ensure_exists(conn, guild_id=guild_id, user_id=user_id)
            if profile.last_daily_claim == claim_date:
                return DailyClaimInfo(
                    claimed=False,
                    amount=0,
                    balance=profile.balance,
                    last_daily_claim=profile.last_daily_claim,
                )

            updated = await EconomyProfilesRepo.claim_daily(
                conn,
                guild_id=guild_id,
                user_id=user_id,
                amount=amount,
                claim_date=claim_date,
            )
            return DailyClaimInfo(
                claimed=True,
                amount=amount,
                balance=updated.balance,
                last_daily_claim=updated.last_daily_claim,
            )

    async def buy_item(
        self,
        *,
        guild_id: int,
        guild_name: str | None,
        discord_user_id: int,
        item_name: str,
        price: int,
    ) -> PurchaseInfo:
        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            user_id = await UserRepo.ensure_exists(conn, discord_id=discord_user_id)
            await EconomyProfilesRepo.ensure_exists(conn, guild_id=guild_id, user_id=user_id)
            profile = await EconomyProfilesRepo.spend_if_enough(
                conn,
                guild_id=guild_id,
                user_id=user_id,
                amount=price,
            )
            if profile is None:
                current = await EconomyProfilesRepo.get_for_update(conn, guild_id=guild_id, user_id=user_id)
                return PurchaseInfo(
                    purchased=False,
                    balance=current.balance if current else 0,
                    item_name=item_name,
                )

            await EconomyInventoryRepo.add_item(
                conn,
                guild_id=guild_id,
                user_id=user_id,
                item_name=item_name,
            )
            return PurchaseInfo(purchased=True, balance=profile.balance, item_name=item_name)

    async def list_inventory(
        self,
        *,
        guild_id: int,
        guild_name: str | None,
        discord_user_id: int,
    ) -> tuple[EconomyProfileInfo, tuple[EconomyInventoryItemInfo, ...]]:
        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            user_id = await UserRepo.ensure_exists(conn, discord_id=discord_user_id)
            profile = await EconomyProfilesRepo.ensure_exists(conn, guild_id=guild_id, user_id=user_id)
            items = await EconomyInventoryRepo.list_for_user(conn, guild_id=guild_id, user_id=user_id)
            return (
                EconomyProfileInfo(
                    guild_id=profile.guild_id,
                    discord_user_id=discord_user_id,
                    balance=profile.balance,
                    last_daily_claim=profile.last_daily_claim,
                ),
                tuple(EconomyInventoryItemInfo(item.item_name, item.quantity) for item in items),
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
        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            from_user_id = await UserRepo.ensure_exists(conn, discord_id=from_discord_user_id)
            to_user_id = await UserRepo.ensure_exists(conn, discord_id=to_discord_user_id)
            await EconomyProfilesRepo.ensure_exists(conn, guild_id=guild_id, user_id=from_user_id)
            await EconomyProfilesRepo.ensure_exists(conn, guild_id=guild_id, user_id=to_user_id)

            removed = await EconomyInventoryRepo.remove_one(
                conn,
                guild_id=guild_id,
                user_id=from_user_id,
                item_name=item_name,
            )
            if not removed:
                return TransferInfo(transferred=False, item_name=item_name)

            await EconomyInventoryRepo.add_item(
                conn,
                guild_id=guild_id,
                user_id=to_user_id,
                item_name=item_name,
            )
            return TransferInfo(transferred=True, item_name=item_name)
