from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import asyncpg

from database.repos.guilds_repo import GuildsRepo
from database.repos.tournament_teams_repo import TournamentTeamsRepo
from database.repos.tournaments_repo import TournamentsRepo
from database.repos.user_repo import UserRepo


@dataclass(frozen=True, slots=True)
class TournamentInfo:
    id: int
    guild_id: int
    tournament_name: str
    max_teams: int
    registration_start: datetime
    registration_end: datetime
    tournament_date: datetime
    status: str
    registration_channel_id: Optional[int]
    registration_message_id: Optional[int]


@dataclass(frozen=True, slots=True)
class TournamentTeamInfo:
    id: int
    tournament_id: int
    team_name: str
    player_discord_ids: tuple[int, ...]
    substitute_discord_ids: tuple[int, ...]
    coach_discord_id: Optional[int]


@dataclass(frozen=True, slots=True)
class RegisterTeamResult:
    status: str
    team: TournamentTeamInfo | None = None


class TournamentsDbService:
    def __init__(self, db) -> None:
        self._db = db

    @staticmethod
    def _tournament_info(row) -> TournamentInfo:
        return TournamentInfo(
            id=row.id,
            guild_id=row.guild_id,
            tournament_name=row.tournament_name,
            max_teams=row.max_teams,
            registration_start=row.registration_start,
            registration_end=row.registration_end,
            tournament_date=row.tournament_date,
            status=row.status,
            registration_channel_id=row.registration_channel_id,
            registration_message_id=row.registration_message_id,
        )

    @staticmethod
    def _team_info(row) -> TournamentTeamInfo:
        return TournamentTeamInfo(
            id=row.id,
            tournament_id=row.tournament_id,
            team_name=row.team_name,
            player_discord_ids=row.player_discord_ids,
            substitute_discord_ids=row.substitute_discord_ids,
            coach_discord_id=row.coach_discord_id,
        )

    async def get_active(self, guild_id: int) -> TournamentInfo | None:
        async with self._db.acquire() as conn:
            row = await TournamentsRepo.get_active(conn, guild_id)
            return self._tournament_info(row) if row else None

    async def create(
        self,
        *,
        guild_id: int,
        guild_name: str | None,
        tournament_name: str,
        max_teams: int,
        registration_start: datetime,
        registration_end: datetime,
        tournament_date: datetime,
    ) -> TournamentInfo | None:
        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            if await TournamentsRepo.get_active(conn, guild_id):
                return None
            try:
                row = await TournamentsRepo.create(
                    conn,
                    guild_id=guild_id,
                    tournament_name=tournament_name,
                    max_teams=max_teams,
                    registration_start=registration_start,
                    registration_end=registration_end,
                    tournament_date=tournament_date,
                )
            except asyncpg.UniqueViolationError:
                return None
            return self._tournament_info(row)

    async def set_registration_message(
        self,
        *,
        tournament_id: int,
        channel_id: int,
        message_id: int,
    ) -> TournamentInfo | None:
        async with self._db.transaction() as conn:
            row = await TournamentsRepo.set_registration_message(
                conn,
                tournament_id=tournament_id,
                channel_id=channel_id,
                message_id=message_id,
            )
            return self._tournament_info(row) if row else None

    async def close_active(self, guild_id: int) -> bool:
        async with self._db.transaction() as conn:
            return await TournamentsRepo.close_active(conn, guild_id)

    async def register_team(
        self,
        *,
        guild_id: int,
        guild_name: str | None,
        tournament_id: int,
        captain_discord_id: int,
        team_name: str,
        player_discord_ids: tuple[int, ...],
        substitute_discord_ids: tuple[int, ...],
        coach_discord_id: Optional[int],
    ) -> RegisterTeamResult:
        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            tournament = await TournamentsRepo.get_by_id(conn, tournament_id)
            if not tournament or tournament.guild_id != guild_id or tournament.status != "active":
                return RegisterTeamResult(status="not_active")

            team_count = await TournamentTeamsRepo.count_for_tournament(conn, tournament_id)
            if team_count >= tournament.max_teams:
                return RegisterTeamResult(status="full")

            captain_user_id = await UserRepo.ensure_exists(conn, discord_id=captain_discord_id)
            try:
                team = await TournamentTeamsRepo.insert(
                    conn,
                    tournament_id=tournament_id,
                    guild_id=guild_id,
                    captain_user_id=captain_user_id,
                    team_name=team_name,
                    player_discord_ids=player_discord_ids,
                    substitute_discord_ids=substitute_discord_ids,
                    coach_discord_id=coach_discord_id,
                )
            except asyncpg.UniqueViolationError:
                return RegisterTeamResult(status="duplicate")

            return RegisterTeamResult(status="created", team=self._team_info(team))
