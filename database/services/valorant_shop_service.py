from __future__ import annotations

from database.repos.guilds_repo import GuildsRepo
from database.repos.valorant_sent_bundles_repo import ValorantSentBundlesRepo


class ValorantShopDbService:
    def __init__(self, db) -> None:
        self._db = db

    async def is_bundle_sent(self, *, guild_id: int, bundle_uuid: str) -> bool:
        async with self._db.acquire() as conn:
            return await ValorantSentBundlesRepo.exists(
                conn,
                guild_id=guild_id,
                bundle_uuid=bundle_uuid,
            )

    async def mark_bundle_sent(
        self,
        *,
        guild_id: int,
        guild_name: str | None,
        bundle_uuid: str,
    ) -> bool:
        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            return await ValorantSentBundlesRepo.insert(
                conn,
                guild_id=guild_id,
                bundle_uuid=bundle_uuid,
            )
