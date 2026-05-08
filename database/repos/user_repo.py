# database\repos\user_repo.py

import asyncpg
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class UserRow:
    user_id: int
    discord_id: int
    last_seen_at: Optional[datetime]


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

    @staticmethod
    async def get_by_discord_id(
        conn: asyncpg.Connection,
        discord_id: int,
    ) -> Optional[UserRow]:
        """Récupère un utilisateur par son discord_id."""
        row = await conn.fetchrow(
            "SELECT user_id, discord_id, last_seen_at FROM users WHERE discord_id = $1;",
            discord_id,
        )
        if not row:
            return None
        return UserRow(
            user_id=row["user_id"],
            discord_id=row["discord_id"],
            last_seen_at=row["last_seen_at"],
        )

    @staticmethod
    async def get_by_user_id(
        conn: asyncpg.Connection,
        user_id: int,
    ) -> Optional[UserRow]:
        """Récupère un utilisateur par son user_id interne."""
        row = await conn.fetchrow(
            "SELECT user_id, discord_id, last_seen_at FROM users WHERE user_id = $1;",
            user_id,
        )
        if not row:
            return None
        return UserRow(
            user_id=row["user_id"],
            discord_id=row["discord_id"],
            last_seen_at=row["last_seen_at"],
        )

    @staticmethod
    async def get_discord_ids_by_user_ids(
        conn: asyncpg.Connection,
        user_ids: list[int],
    ) -> dict[int, int]:
        if not user_ids:
            return {}

        rows = await conn.fetch(
            """
            SELECT user_id, discord_id
              FROM users
             WHERE user_id = ANY($1);
            """,
            user_ids,
        )
        return {row["user_id"]: row["discord_id"] for row in rows}
