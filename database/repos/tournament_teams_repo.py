from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import asyncpg


@dataclass(frozen=True, slots=True)
class TournamentTeamRow:
    id: int
    tournament_id: int
    guild_id: int
    captain_user_id: int
    team_name: str
    player_discord_ids: tuple[int, ...]
    substitute_discord_ids: tuple[int, ...]
    coach_discord_id: Optional[int]


class TournamentTeamsRepo:
    @staticmethod
    def _row_to_model(row: asyncpg.Record) -> TournamentTeamRow:
        return TournamentTeamRow(
            id=int(row["id"]),
            tournament_id=int(row["tournament_id"]),
            guild_id=int(row["guild_id"]),
            captain_user_id=int(row["captain_user_id"]),
            team_name=str(row["team_name"]),
            player_discord_ids=tuple(int(value) for value in row["player_discord_ids"]),
            substitute_discord_ids=tuple(int(value) for value in row["substitute_discord_ids"]),
            coach_discord_id=int(row["coach_discord_id"]) if row["coach_discord_id"] else None,
        )

    @staticmethod
    async def count_for_tournament(conn: asyncpg.Connection, tournament_id: int) -> int:
        return int(
            await conn.fetchval(
                "SELECT count(*) FROM tournament_teams WHERE tournament_id = $1;",
                tournament_id,
            )
            or 0
        )

    @classmethod
    async def insert(
        cls,
        conn: asyncpg.Connection,
        *,
        tournament_id: int,
        guild_id: int,
        captain_user_id: int,
        team_name: str,
        player_discord_ids: tuple[int, ...],
        substitute_discord_ids: tuple[int, ...],
        coach_discord_id: Optional[int],
    ) -> TournamentTeamRow:
        row = await conn.fetchrow(
            """
            INSERT INTO tournament_teams (
              tournament_id, guild_id, captain_user_id, team_name,
              player_discord_ids, substitute_discord_ids, coach_discord_id
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id, tournament_id, guild_id, captain_user_id, team_name,
                      player_discord_ids, substitute_discord_ids, coach_discord_id;
            """,
            tournament_id,
            guild_id,
            captain_user_id,
            team_name,
            list(player_discord_ids),
            list(substitute_discord_ids),
            coach_discord_id,
        )
        return cls._row_to_model(row)
