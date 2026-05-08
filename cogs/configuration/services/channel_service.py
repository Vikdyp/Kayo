# cogs/configuration/services/channel_service.py

from __future__ import annotations

from database.services.guild_channels_service import ChannelConfigurationService as ChannelConfigurationDbService


def normalize_key(k: str) -> str:
    return " ".join(k.strip().split())


class ChannelConfigurationService:
    """
    Service "metier" de configuration des salons.
    Orchestration legere autour du service DB.
    """

    def __init__(self, db_service: ChannelConfigurationDbService):
        self._db_service = db_service

    async def get_all(self, guild_id: int) -> dict[str, int]:
        return await self._db_service.get_all(guild_id)

    async def get_one(self, guild_id: int, key: str) -> int | None:
        return await self._db_service.get_one(guild_id, key)

    async def set_one(self, guild_id: int, guild_name: str | None, key: str, channel_id: int) -> None:
        await self._db_service.set_one(guild_id, guild_name, key, channel_id)

    async def remove_one(self, guild_id: int, key: str) -> bool:
        return await self._db_service.remove_one(guild_id, key)
