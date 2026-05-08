# cogs/configuration/services/role_service.py

from __future__ import annotations

from database.services.guild_roles_service import RoleConfigurationService as RoleConfigurationDbService


def normalize_key(k: str) -> str:
    return " ".join(k.strip().split())


class RoleConfigurationService:
    """
    Service "metier" de configuration des roles.
    Orchestration legere autour du service DB.
    """

    def __init__(self, db_service: RoleConfigurationDbService):
        self._db_service = db_service

    async def get_all(self, guild_id: int) -> dict[str, int]:
        return await self._db_service.get_all(guild_id)

    async def get_one(self, guild_id: int, key: str) -> int | None:
        return await self._db_service.get_one(guild_id, key)

    async def set_one(
        self,
        *,
        guild_id: int,
        guild_name: str | None,
        key: str,
        role_id: int,
        role_name: str,
    ) -> None:
        await self._db_service.set_one(
            guild_id=guild_id,
            guild_name=guild_name,
            key=key,
            role_id=role_id,
            name_cache=role_name,
        )

    async def remove_one(self, guild_id: int, key: str) -> bool:
        return await self._db_service.remove_one(guild_id, key)
