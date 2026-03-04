# database/services/valorant_sent_bundles_service.py

from __future__ import annotations

from database.repos.valorant_sent_bundles_repo import ValorantSentBundlesRepo


class ValorantSentBundlesService:
    def __init__(self, db):
        self._db = db

    async def is_sent(self, bundle_uuid: str) -> bool:
        async with self._db.acquire() as conn:
            return await ValorantSentBundlesRepo.exists(conn, bundle_uuid)

    async def mark_sent(self, bundle_uuid: str) -> None:
        async with self._db.transaction() as conn:
            await ValorantSentBundlesRepo.mark_sent(conn, bundle_uuid)
