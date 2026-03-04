# database/repos/valorant_sent_bundles_repo.py

from __future__ import annotations

import asyncpg


class ValorantSentBundlesRepo:

    @staticmethod
    async def exists(conn: asyncpg.Connection, bundle_uuid: str) -> bool:
        row = await conn.fetchrow(
            "SELECT 1 FROM valorant_sent_bundles WHERE bundle_uuid = $1;",
            bundle_uuid,
        )
        return row is not None

    @staticmethod
    async def mark_sent(conn: asyncpg.Connection, bundle_uuid: str) -> None:
        await conn.execute(
            """
            INSERT INTO valorant_sent_bundles (bundle_uuid, notified_at)
            VALUES ($1, now())
            ON CONFLICT (bundle_uuid) DO NOTHING;
            """,
            bundle_uuid,
        )
