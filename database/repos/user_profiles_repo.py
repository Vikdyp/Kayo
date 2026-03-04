# database/repos/user_profiles_repo.py

from __future__ import annotations

from typing import Optional

import asyncpg


class UserProfilesRepo:

    @staticmethod
    async def get(
        conn: asyncpg.Connection, discord_user_id: int
    ) -> Optional[asyncpg.Record]:
        return await conn.fetchrow(
            """
            SELECT genre, valorant_tracker, lft, note
              FROM user_profiles
             WHERE discord_user_id = $1
            """,
            discord_user_id,
        )

    @staticmethod
    async def upsert(
        conn: asyncpg.Connection,
        discord_user_id: int,
        genre: Optional[str],
        valorant_tracker: Optional[str],
        lft: Optional[str],
        note: Optional[str],
    ) -> None:
        await conn.execute(
            """
            INSERT INTO user_profiles (discord_user_id, genre, valorant_tracker, lft, note)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (discord_user_id)
            DO UPDATE SET
                genre = EXCLUDED.genre,
                valorant_tracker = EXCLUDED.valorant_tracker,
                lft = EXCLUDED.lft,
                note = EXCLUDED.note
            """,
            discord_user_id, genre, valorant_tracker, lft, note,
        )
