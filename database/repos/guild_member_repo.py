# database\repos\guild_member_repo.py

import asyncpg


class GuildMemberRepo:

    @staticmethod
    async def mark_join(
        conn: asyncpg.Connection,
        *,
        guild_id: int,
        user_id: int,
    ) -> None:
        await conn.execute(
            """
            INSERT INTO guild_members(
              guild_id, user_id, is_member, joined_at, left_at
            )
            VALUES ($1, $2, TRUE, now(), NULL)
            ON CONFLICT (guild_id, user_id) DO UPDATE
            SET is_member = TRUE,
                joined_at = COALESCE(guild_members.joined_at, now()),
                left_at = NULL,
                updated_at = now();
            """,
            guild_id,
            user_id,
        )

    @staticmethod
    async def mark_leave(
        conn: asyncpg.Connection,
        *,
        guild_id: int,
        user_id: int,
    ) -> None:
        await conn.execute(
            """
            UPDATE guild_members
            SET is_member = FALSE,
                left_at = now(),
                updated_at = now()
            WHERE guild_id = $1 AND user_id = $2;
            """,
            guild_id,
            user_id,
        )

    @staticmethod
    async def is_member(
        conn: asyncpg.Connection,
        *,
        guild_id: int,
        user_id: int,
    ) -> bool:
        row = await conn.fetchrow(
            """
            SELECT is_member
            FROM guild_members
            WHERE guild_id = $1 AND user_id = $2;
            """,
            guild_id,
            user_id,
        )

        return bool(row["is_member"]) if row else False

    @staticmethod
    async def mark_rules_accepted(conn: asyncpg.Connection, *, guild_id: int, user_id: int) -> None:
        await conn.execute(
            """
            UPDATE guild_members
            SET accepted_rules = TRUE,
                accepted_rules_at = now(),
                updated_at = now()
            WHERE guild_id = $1 AND user_id = $2;
            """,
            guild_id,
            user_id,
        )

    @staticmethod
    async def mark_rules_revoked(conn: asyncpg.Connection, *, guild_id: int, user_id: int) -> None:
        """
        Optionnel: si tu veux pouvoir "reset" l'acceptation.
        """
        await conn.execute(
            """
            UPDATE guild_members
            SET accepted_rules = FALSE,
                accepted_rules_at = NULL,
                updated_at = now()
            WHERE guild_id = $1 AND user_id = $2;
            """,
            guild_id,
            user_id,
        )

    @staticmethod
    async def has_accepted_rules(conn: asyncpg.Connection, *, guild_id: int, user_id: int) -> bool:
        row = await conn.fetchrow(
            """
            SELECT accepted_rules
            FROM guild_members
            WHERE guild_id = $1 AND user_id = $2;
            """,
            guild_id,
            user_id,
        )
        return bool(row["accepted_rules"]) if row else False