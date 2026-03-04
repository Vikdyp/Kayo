# database/services/role_combinations_service.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from database.repos.guilds_repo import GuildsRepo
from database.repos.role_combinations_repo import RoleCombinationsRepo


@dataclass(frozen=True)
class RoleCombinationInfo:
    primary_role_id: int
    secondary_role_id: int
    combined_role_id: int


class RoleCombinationsService:
    def __init__(self, db):
        self._db = db

    async def get_all(self, guild_id: int) -> list[RoleCombinationInfo]:
        async with self._db.acquire() as conn:
            rows = await RoleCombinationsRepo.get_all(conn, guild_id)
            return [
                RoleCombinationInfo(
                    primary_role_id=r["primary_role_id"],
                    secondary_role_id=r["secondary_role_id"],
                    combined_role_id=r["combined_role_id"],
                )
                for r in rows
            ]

    async def add(
        self,
        guild_id: int,
        guild_name: Optional[str],
        primary_role_id: int,
        secondary_role_id: int,
        combined_role_id: int,
    ) -> None:
        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            await RoleCombinationsRepo.upsert(
                conn, guild_id, primary_role_id, secondary_role_id, combined_role_id
            )

    async def remove(
        self,
        guild_id: int,
        primary_role_id: int,
        secondary_role_id: int,
    ) -> bool:
        async with self._db.transaction() as conn:
            return await RoleCombinationsRepo.delete(
                conn, guild_id, primary_role_id, secondary_role_id
            )
