from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from database.services.guild_channels_service import ChannelConfigurationService
from database.services.tournaments_service import RegisterTeamResult, TournamentsDbService

REGISTRATION_CHANNEL_KEY = "inscription_tournament_channel_id"
TOURNAMENT_PUBLIC_CHANNEL_KEY = "tournament_channel_id"


@dataclass(frozen=True, slots=True)
class ParsedTeamRegistration:
    team_name: str
    player_discord_ids: tuple[int, ...]
    substitute_discord_ids: tuple[int, ...]
    coach_discord_id: int | None


class TournamentService:
    def __init__(
        self,
        tournaments_db_service: TournamentsDbService,
        channel_config_service: ChannelConfigurationService,
    ) -> None:
        self._tournaments = tournaments_db_service
        self._channels = channel_config_service

    async def get_active_tournament(self, guild_id: int):
        return await self._tournaments.get_active(guild_id)

    async def create_tournament(
        self,
        *,
        guild_id: int,
        guild_name: str | None,
        tournament_name: str,
        max_teams: int,
        registration_start: datetime,
        registration_end: datetime,
        tournament_date: datetime,
    ):
        if max_teams <= 0 or registration_end < registration_start:
            return None
        return await self._tournaments.create(
            guild_id=guild_id,
            guild_name=guild_name,
            tournament_name=tournament_name.strip(),
            max_teams=max_teams,
            registration_start=registration_start,
            registration_end=registration_end,
            tournament_date=tournament_date,
        )

    async def save_registration_message(self, *, tournament_id: int, channel_id: int, message_id: int):
        return await self._tournaments.set_registration_message(
            tournament_id=tournament_id,
            channel_id=channel_id,
            message_id=message_id,
        )

    async def close_active_tournament(self, guild_id: int) -> bool:
        return await self._tournaments.close_active(guild_id)

    async def register_team(
        self,
        *,
        guild_id: int,
        guild_name: str | None,
        tournament_id: int,
        captain_discord_id: int,
        registration: ParsedTeamRegistration,
    ) -> RegisterTeamResult:
        return await self._tournaments.register_team(
            guild_id=guild_id,
            guild_name=guild_name,
            tournament_id=tournament_id,
            captain_discord_id=captain_discord_id,
            team_name=registration.team_name,
            player_discord_ids=registration.player_discord_ids,
            substitute_discord_ids=registration.substitute_discord_ids,
            coach_discord_id=registration.coach_discord_id,
        )

    async def get_registration_channel_id(self, guild_id: int) -> int | None:
        return await self._channels.get_one(guild_id, REGISTRATION_CHANNEL_KEY)

    async def get_public_channel_id(self, guild_id: int) -> int | None:
        return await self._channels.get_one(guild_id, TOURNAMENT_PUBLIC_CHANNEL_KEY)

    @staticmethod
    def parse_team_registration(
        *,
        team_name: str,
        players_raw: str,
        extras_raw: str,
    ) -> ParsedTeamRegistration:
        name = " ".join(team_name.strip().split())
        if not name:
            raise ValueError("team_name")

        players = _parse_discord_id_list(players_raw)
        if len(players) != 5:
            raise ValueError("players")

        extras = _parse_discord_id_list(extras_raw)[:3]
        return ParsedTeamRegistration(
            team_name=name,
            player_discord_ids=tuple(players),
            substitute_discord_ids=tuple(extras[:2]),
            coach_discord_id=extras[2] if len(extras) >= 3 else None,
        )


def _parse_discord_id_list(raw: str) -> list[int]:
    if not raw.strip():
        return []

    result: list[int] = []
    for value in raw.split(","):
        cleaned = value.strip().removeprefix("<@").removeprefix("!").removesuffix(">")
        if not cleaned:
            continue
        if not cleaned.isdigit():
            raise ValueError("discord_id")
        result.append(int(cleaned))
    return result
