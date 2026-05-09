from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

import asyncpg


@dataclass(frozen=True, slots=True)
class EconomyProfileRow:
    guild_id: int
    user_id: int
    balance: int
    last_daily_claim: Optional[date]


class EconomyProfilesRepo:
    @staticmethod
    def _row_to_model(row: asyncpg.Record) -> EconomyProfileRow:
        return EconomyProfileRow(
            guild_id=int(row["guild_id"]),
            user_id=int(row["user_id"]),
            balance=int(row["balance"]),
            last_daily_claim=row["last_daily_claim"],
        )

    @classmethod
    async def ensure_exists(
        cls,
        conn: asyncpg.Connection,
        *,
        guild_id: int,
        user_id: int,
    ) -> EconomyProfileRow:
        row = await conn.fetchrow(
            """
            INSERT INTO economy_profiles (guild_id, user_id)
            VALUES ($1, $2)
            ON CONFLICT (guild_id, user_id) DO UPDATE
              SET updated_at = economy_profiles.updated_at
            RETURNING guild_id, user_id, balance, last_daily_claim;
            """,
            guild_id,
            user_id,
        )
        return cls._row_to_model(row)

    @classmethod
    async def get_for_update(
        cls,
        conn: asyncpg.Connection,
        *,
        guild_id: int,
        user_id: int,
    ) -> Optional[EconomyProfileRow]:
        row = await conn.fetchrow(
            """
            SELECT guild_id, user_id, balance, last_daily_claim
              FROM economy_profiles
             WHERE guild_id = $1
               AND user_id = $2
             FOR UPDATE;
            """,
            guild_id,
            user_id,
        )
        return cls._row_to_model(row) if row else None

    @classmethod
    async def claim_daily(
        cls,
        conn: asyncpg.Connection,
        *,
        guild_id: int,
        user_id: int,
        amount: int,
        claim_date: date,
    ) -> EconomyProfileRow:
        row = await conn.fetchrow(
            """
            UPDATE economy_profiles
               SET balance = balance + $3,
                   last_daily_claim = $4,
                   updated_at = now()
             WHERE guild_id = $1
               AND user_id = $2
            RETURNING guild_id, user_id, balance, last_daily_claim;
            """,
            guild_id,
            user_id,
            amount,
            claim_date,
        )
        return cls._row_to_model(row)

    @classmethod
    async def spend_if_enough(
        cls,
        conn: asyncpg.Connection,
        *,
        guild_id: int,
        user_id: int,
        amount: int,
    ) -> Optional[EconomyProfileRow]:
        row = await conn.fetchrow(
            """
            UPDATE economy_profiles
               SET balance = balance - $3,
                   updated_at = now()
             WHERE guild_id = $1
               AND user_id = $2
               AND balance >= $3
            RETURNING guild_id, user_id, balance, last_daily_claim;
            """,
            guild_id,
            user_id,
            amount,
        )
        return cls._row_to_model(row) if row else None
