from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import asyncpg


@dataclass(frozen=True, slots=True)
class FiveStackMatchRow:
    id: int
    guild_id: int
    match_code: str
    voice_channel_id: Optional[int]
    quality_score: float
    elo_spread: int
    avg_elo: int
    role_diversity_score: float
    total_wait_time_seconds: int
    team_size: int
    language: Optional[str]
    region: Optional[str]
    platform: Optional[str]
    created_at: datetime


class FiveStackMatchesRepo:
    @staticmethod
    def _row_to_model(row: asyncpg.Record) -> FiveStackMatchRow:
        return FiveStackMatchRow(
            id=int(row["id"]),
            guild_id=int(row["guild_id"]),
            match_code=str(row["match_code"]),
            voice_channel_id=int(row["voice_channel_id"]) if row["voice_channel_id"] else None,
            quality_score=float(row["quality_score"]),
            elo_spread=int(row["elo_spread"]),
            avg_elo=int(row["avg_elo"]),
            role_diversity_score=float(row["role_diversity_score"]),
            total_wait_time_seconds=int(row["total_wait_time_seconds"]),
            team_size=int(row["team_size"]),
            language=str(row["language"]) if row["language"] else None,
            region=str(row["region"]) if row["region"] else None,
            platform=str(row["platform"]) if row["platform"] else None,
            created_at=row["created_at"],
        )

    @classmethod
    async def create(
        cls,
        conn: asyncpg.Connection,
        *,
        guild_id: int,
        match_code: str,
        voice_channel_id: int | None,
        quality_score: float,
        elo_spread: int,
        avg_elo: int,
        role_diversity_score: float,
        total_wait_time_seconds: int,
        team_size: int,
        language: str | None,
        region: str | None,
        platform: str | None,
    ) -> FiveStackMatchRow:
        row = await conn.fetchrow(
            """
            INSERT INTO five_stack_matches (
              guild_id, match_code, voice_channel_id, quality_score, elo_spread,
              avg_elo, role_diversity_score, total_wait_time_seconds,
              team_size, language, region, platform
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            RETURNING id, guild_id, match_code, voice_channel_id, quality_score,
                      elo_spread, avg_elo, role_diversity_score,
                      total_wait_time_seconds, team_size, language, region,
                      platform, created_at;
            """,
            guild_id,
            match_code,
            voice_channel_id,
            quality_score,
            elo_spread,
            avg_elo,
            role_diversity_score,
            total_wait_time_seconds,
            team_size,
            language,
            region,
            platform,
        )
        return cls._row_to_model(row)

    @classmethod
    async def get_by_id(cls, conn: asyncpg.Connection, match_id: int) -> FiveStackMatchRow | None:
        row = await conn.fetchrow(
            """
            SELECT id, guild_id, match_code, voice_channel_id, quality_score,
                   elo_spread, avg_elo, role_diversity_score,
                   total_wait_time_seconds, team_size, language, region,
                   platform, created_at
              FROM five_stack_matches
             WHERE id = $1;
            """,
            match_id,
        )
        return cls._row_to_model(row) if row else None

    @classmethod
    async def list_by_guild(cls, conn: asyncpg.Connection, *, guild_id: int, limit: int) -> list[FiveStackMatchRow]:
        rows = await conn.fetch(
            """
            SELECT id, guild_id, match_code, voice_channel_id, quality_score,
                   elo_spread, avg_elo, role_diversity_score,
                   total_wait_time_seconds, team_size, language, region,
                   platform, created_at
              FROM five_stack_matches
             WHERE guild_id = $1
             ORDER BY created_at DESC
             LIMIT $2;
            """,
            guild_id,
            limit,
        )
        return [cls._row_to_model(row) for row in rows]

    @staticmethod
    async def server_stats(conn: asyncpg.Connection, guild_id: int) -> dict:
        row = await conn.fetchrow(
            """
            SELECT COUNT(*) AS total_matches,
                   COALESCE(AVG(quality_score), 0) AS avg_quality_score,
                   COALESCE(AVG(elo_spread), 0) AS avg_elo_spread,
                   COALESCE(AVG(total_wait_time_seconds), 0) AS avg_wait_time_seconds,
                   COUNT(*) FILTER (WHERE created_at > now() - INTERVAL '1 day') AS matches_today,
                   COUNT(*) FILTER (WHERE created_at > now() - INTERVAL '7 days') AS matches_this_week
              FROM five_stack_matches
             WHERE guild_id = $1;
            """,
            guild_id,
        )
        return dict(row) if row else {}

    @staticmethod
    async def size_distribution(conn: asyncpg.Connection, guild_id: int) -> dict[int, int]:
        rows = await conn.fetch(
            """
            SELECT team_size, COUNT(*) AS count
              FROM five_stack_matches
             WHERE guild_id = $1
             GROUP BY team_size;
            """,
            guild_id,
        )
        return {int(row["team_size"]): int(row["count"]) for row in rows}
