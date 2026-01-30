# database\repos\user_repo.py

import asyncpg
from typing import Optional


class UserRepo:

    @staticmethod
    async def ensure_exists(
        conn: asyncpg.Connection,
        *,
        discord_id: int,
    ) -> int:
        """
        Ensure user exists and return user_id.
        """
        row = await conn.fetchrow(
            """
            INSERT INTO users(discord_id)
            VALUES ($1)
            ON CONFLICT (discord_id) DO UPDATE
            SET last_seen_at = now()
            RETURNING user_id;
            """,
            discord_id,
        )

        return int(row["user_id"])

    @staticmethod
    async def get_user_id(
        conn: asyncpg.Connection,
        discord_id: int,
    ) -> Optional[int]:
        row = await conn.fetchrow(
            "SELECT user_id FROM users WHERE discord_id = $1;",
            discord_id,
        )
        return int(row["user_id"]) if row else None

    @staticmethod
    async def touch_seen(conn: asyncpg.Connection, user_id: int) -> None:
        await conn.execute(
            "UPDATE users SET last_seen_at = now() WHERE user_id = $1;",
            user_id,
        )
