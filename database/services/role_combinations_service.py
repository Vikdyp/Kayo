from __future__ import annotations

from database.repos.guilds_repo import GuildsRepo
from database.repos.role_combinations_repo import RoleCombinationRow, RoleCombinationsRepo


class RoleCombinationsDbService:
    def __init__(self, db) -> None:
        self._db = db

    async def list_combinations(self, guild_id: int) -> list[RoleCombinationRow]:
        async with self._db.acquire() as conn:
            return await RoleCombinationsRepo.list_by_guild(conn, guild_id)

    async def save_combination(
        self,
        *,
        guild_id: int,
        guild_name: str | None,
        primary_role_id: int,
        secondary_role_id: int,
        combined_role_id: int,
    ) -> None:
        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            await RoleCombinationsRepo.upsert(
                conn,
                guild_id=guild_id,
                primary_role_id=primary_role_id,
                secondary_role_id=secondary_role_id,
                combined_role_id=combined_role_id,
            )

    async def delete_combination(
        self,
        *,
        guild_id: int,
        primary_role_id: int,
        secondary_role_id: int,
    ) -> bool:
        async with self._db.transaction() as conn:
            return await RoleCombinationsRepo.delete(
                conn,
                guild_id=guild_id,
                primary_role_id=primary_role_id,
                secondary_role_id=secondary_role_id,
            )
