# database/repos/economy_repo.py

from __future__ import annotations

from datetime import datetime
from typing import Optional

import asyncpg


class EconomyRepo:

    @staticmethod
    async def ensure_user(conn: asyncpg.Connection, discord_user_id: int) -> None:
        await conn.execute(
            """
            INSERT INTO user_economy (discord_user_id)
            VALUES ($1)
            ON CONFLICT (discord_user_id) DO NOTHING
            """,
            discord_user_id,
        )

    @staticmethod
    async def get_balance(conn: asyncpg.Connection, discord_user_id: int) -> Optional[asyncpg.Record]:
        return await conn.fetchrow(
            "SELECT balance, last_claim FROM user_economy WHERE discord_user_id = $1",
            discord_user_id,
        )

    @staticmethod
    async def add_balance(conn: asyncpg.Connection, discord_user_id: int, amount: int) -> int:
        return await conn.fetchval(
            """
            UPDATE user_economy
               SET balance = balance + $2, last_claim = NOW()
             WHERE discord_user_id = $1
             RETURNING balance
            """,
            discord_user_id, amount,
        )

    @staticmethod
    async def subtract_balance(conn: asyncpg.Connection, discord_user_id: int, amount: int) -> Optional[int]:
        return await conn.fetchval(
            """
            UPDATE user_economy
               SET balance = balance - $2
             WHERE discord_user_id = $1 AND balance >= $2
             RETURNING balance
            """,
            discord_user_id, amount,
        )

    @staticmethod
    async def get_items(conn: asyncpg.Connection, discord_user_id: int) -> list[str]:
        rows = await conn.fetch(
            "SELECT item_name FROM user_inventory WHERE discord_user_id = $1 ORDER BY acquired_at",
            discord_user_id,
        )
        return [r["item_name"] for r in rows]

    @staticmethod
    async def add_item(conn: asyncpg.Connection, discord_user_id: int, item_name: str) -> None:
        await conn.execute(
            "INSERT INTO user_inventory (discord_user_id, item_name) VALUES ($1, $2)",
            discord_user_id, item_name,
        )

    @staticmethod
    async def remove_item(conn: asyncpg.Connection, discord_user_id: int, item_name: str) -> bool:
        result = await conn.execute(
            """
            DELETE FROM user_inventory
             WHERE id = (
                SELECT id FROM user_inventory
                 WHERE discord_user_id = $1 AND item_name = $2
                 LIMIT 1
             )
            """,
            discord_user_id, item_name,
        )
        return not result.endswith("0")
