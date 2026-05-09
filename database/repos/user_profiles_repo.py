from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import asyncpg


@dataclass(frozen=True, slots=True)
class UserProfileRow:
    user_id: int
    genre: Optional[str]
    valorant_tracker: Optional[str]
    lft: Optional[str]
    note: Optional[str]


class UserProfilesRepo:
    @staticmethod
    async def get(conn: asyncpg.Connection, user_id: int) -> Optional[UserProfileRow]:
        row = await conn.fetchrow(
            """
            SELECT user_id, genre, valorant_tracker, lft, note
              FROM user_profiles
             WHERE user_id = $1;
            """,
            user_id,
        )
        if not row:
            return None
        return UserProfileRow(
            user_id=int(row["user_id"]),
            genre=row["genre"],
            valorant_tracker=row["valorant_tracker"],
            lft=row["lft"],
            note=row["note"],
        )

    @staticmethod
    async def upsert(
        conn: asyncpg.Connection,
        *,
        user_id: int,
        genre: str | None,
        valorant_tracker: str | None,
        lft: str | None,
        note: str | None,
    ) -> None:
        await conn.execute(
            """
            INSERT INTO user_profiles (user_id, genre, valorant_tracker, lft, note)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (user_id) DO UPDATE
              SET genre = EXCLUDED.genre,
                  valorant_tracker = EXCLUDED.valorant_tracker,
                  lft = EXCLUDED.lft,
                  note = EXCLUDED.note,
                  updated_at = now();
            """,
            user_id,
            genre,
            valorant_tracker,
            lft,
            note,
        )
