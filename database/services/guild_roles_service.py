# database\services\guild_roles_service.py

from database.repos.guilds_repo import GuildsRepo
from database.repos.guild_roles_repo import GuildRolesRepo

def normalize_key(k: str) -> str:
    return " ".join(k.strip().split())

class RoleConfigurationService:
    def __init__(self, db):
        self._db = db

    async def get_all(self, guild_id: int) -> dict[str, int]:
        async with self._db.acquire() as conn:
            return await GuildRolesRepo.get_all(conn, guild_id)

    async def get_one(self, guild_id: int, key: str) -> int | None:
        key = normalize_key(key)
        async with self._db.acquire() as conn:
            return await GuildRolesRepo.get(conn, guild_id, key)

    async def set_one(self, guild_id: int, guild_name: str | None, key: str, role_id: int, name_cache: str) -> None:
        key = normalize_key(key)
        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            await GuildRolesRepo.upsert(conn, guild_id, key, role_id, name_cache)

    async def remove_one(self, guild_id: int, key: str) -> bool:
        key = normalize_key(key)
        async with self._db.transaction() as conn:
            return await GuildRolesRepo.delete(conn, guild_id, key)
