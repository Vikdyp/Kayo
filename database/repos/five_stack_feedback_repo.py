from __future__ import annotations

import asyncpg


class FiveStackFeedbackRepo:
    @staticmethod
    async def upsert(
        conn: asyncpg.Connection,
        *,
        match_id: int,
        reporter_id: int,
        rating: int,
        feedback_type: str,
        issues: tuple[str, ...],
        comment: str | None,
    ) -> None:
        await conn.execute(
            """
            INSERT INTO five_stack_feedback (
              match_id, reporter_id, rating, feedback_type, issues, comment
            )
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (match_id, reporter_id) DO UPDATE SET
              rating = EXCLUDED.rating,
              feedback_type = EXCLUDED.feedback_type,
              issues = EXCLUDED.issues,
              comment = EXCLUDED.comment,
              created_at = now();
            """,
            match_id,
            reporter_id,
            rating,
            feedback_type,
            list(issues) if issues else None,
            comment,
        )

    @staticmethod
    async def has_feedback(conn: asyncpg.Connection, *, match_id: int, reporter_id: int) -> bool:
        return bool(
            await conn.fetchval(
                """
                SELECT EXISTS(
                    SELECT 1
                      FROM five_stack_feedback
                     WHERE match_id = $1
                       AND reporter_id = $2
                );
                """,
                match_id,
                reporter_id,
            )
        )
