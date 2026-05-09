from __future__ import annotations

from dataclasses import dataclass

import asyncpg


@dataclass(frozen=True, slots=True)
class TwitchStreamerRow:
    guild_id: int
    streamer_login: str


class TwitchStreamersRepo:
    @staticmethod
    async def insert(conn: asyncpg.Connection, *, guild_id: int, streamer_login: str) -> bool:
        row = await conn.fetchrow(
            """
            INSERT INTO twitch_streamers (guild_id, streamer_login)
            VALUES ($1, $2)
            ON CONFLICT (guild_id, streamer_login) DO NOTHING
            RETURNING streamer_login;
            """,
            guild_id,
            streamer_login,
        )
        return row is not None

    @staticmethod
    async def delete(conn: asyncpg.Connection, *, guild_id: int, streamer_login: str) -> bool:
        result = await conn.execute(
            """
            DELETE FROM twitch_streamers
             WHERE guild_id = $1
               AND streamer_login = $2;
            """,
            guild_id,
            streamer_login,
        )
        return result.startswith("DELETE ") and not result.endswith(" 0")

    @staticmethod
    async def list_by_guild(conn: asyncpg.Connection, guild_id: int) -> list[TwitchStreamerRow]:
        rows = await conn.fetch(
            """
            SELECT guild_id, streamer_login
              FROM twitch_streamers
             WHERE guild_id = $1
             ORDER BY streamer_login;
            """,
            guild_id,
        )
        return [
            TwitchStreamerRow(
                guild_id=int(row["guild_id"]),
                streamer_login=str(row["streamer_login"]),
            )
            for row in rows
        ]
