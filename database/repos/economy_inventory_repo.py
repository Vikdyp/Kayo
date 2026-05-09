from __future__ import annotations

from dataclasses import dataclass

import asyncpg


@dataclass(frozen=True, slots=True)
class EconomyInventoryItemRow:
    guild_id: int
    user_id: int
    item_name: str
    quantity: int


class EconomyInventoryRepo:
    @staticmethod
    def _row_to_model(row: asyncpg.Record) -> EconomyInventoryItemRow:
        return EconomyInventoryItemRow(
            guild_id=int(row["guild_id"]),
            user_id=int(row["user_id"]),
            item_name=str(row["item_name"]),
            quantity=int(row["quantity"]),
        )

    @classmethod
    async def list_for_user(
        cls,
        conn: asyncpg.Connection,
        *,
        guild_id: int,
        user_id: int,
    ) -> list[EconomyInventoryItemRow]:
        rows = await conn.fetch(
            """
            SELECT guild_id, user_id, item_name, quantity
              FROM economy_inventory_items
             WHERE guild_id = $1
               AND user_id = $2
             ORDER BY item_name;
            """,
            guild_id,
            user_id,
        )
        return [cls._row_to_model(row) for row in rows]

    @classmethod
    async def add_item(
        cls,
        conn: asyncpg.Connection,
        *,
        guild_id: int,
        user_id: int,
        item_name: str,
        quantity: int = 1,
    ) -> EconomyInventoryItemRow:
        row = await conn.fetchrow(
            """
            INSERT INTO economy_inventory_items (guild_id, user_id, item_name, quantity)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id, user_id, item_name) DO UPDATE
              SET quantity = economy_inventory_items.quantity + EXCLUDED.quantity,
                  updated_at = now()
            RETURNING guild_id, user_id, item_name, quantity;
            """,
            guild_id,
            user_id,
            item_name,
            quantity,
        )
        return cls._row_to_model(row)

    @classmethod
    async def remove_one(
        cls,
        conn: asyncpg.Connection,
        *,
        guild_id: int,
        user_id: int,
        item_name: str,
    ) -> bool:
        updated = await conn.fetchrow(
            """
            UPDATE economy_inventory_items
               SET quantity = quantity - 1,
                   updated_at = now()
             WHERE guild_id = $1
               AND user_id = $2
               AND item_name = $3
               AND quantity > 1
            RETURNING quantity;
            """,
            guild_id,
            user_id,
            item_name,
        )
        if updated:
            return True

        deleted = await conn.fetchrow(
            """
            DELETE FROM economy_inventory_items
             WHERE guild_id = $1
               AND user_id = $2
               AND item_name = $3
               AND quantity = 1
            RETURNING item_name;
            """,
            guild_id,
            user_id,
            item_name,
        )
        return deleted is not None
