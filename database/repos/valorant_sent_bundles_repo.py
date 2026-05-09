from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import asyncpg


@dataclass(frozen=True, slots=True)
class ValorantSentBundleRow:
    guild_id: int
    bundle_uuid: str
    notified_at: datetime


class ValorantSentBundlesRepo:
    @staticmethod
    async def get(
        conn: asyncpg.Connection,
        *,
        guild_id: int,
        bundle_uuid: str,
    ) -> Optional[ValorantSentBundleRow]:
        row = await conn.fetchrow(
            """
            SELECT guild_id, bundle_uuid, notified_at
              FROM valorant_sent_bundles
             WHERE guild_id = $1
               AND bundle_uuid = $2;
            """,
            guild_id,
            bundle_uuid,
        )
        if row is None:
            return None

        return ValorantSentBundleRow(
            guild_id=int(row["guild_id"]),
            bundle_uuid=str(row["bundle_uuid"]),
            notified_at=row["notified_at"],
        )

    @staticmethod
    async def exists(
        conn: asyncpg.Connection,
        *,
        guild_id: int,
        bundle_uuid: str,
    ) -> bool:
        return bool(
            await conn.fetchval(
                """
                SELECT EXISTS(
                    SELECT 1
                      FROM valorant_sent_bundles
                     WHERE guild_id = $1
                       AND bundle_uuid = $2
                );
                """,
                guild_id,
                bundle_uuid,
            )
        )

    @staticmethod
    async def insert(
        conn: asyncpg.Connection,
        *,
        guild_id: int,
        bundle_uuid: str,
    ) -> bool:
        row = await conn.fetchrow(
            """
            INSERT INTO valorant_sent_bundles (guild_id, bundle_uuid)
            VALUES ($1, $2)
            ON CONFLICT (guild_id, bundle_uuid) DO NOTHING
            RETURNING guild_id;
            """,
            guild_id,
            bundle_uuid,
        )
        return row is not None
