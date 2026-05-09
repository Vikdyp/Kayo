from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from database.services.persistent_messages_service import PersistentMessageInfo, PersistentMessagesService
from database.services.scrims_service import ScrimInfo, ScrimJoinResult, ScrimLeaveResult, ScrimsDbService

SCRIM_CREATION_MESSAGE_TYPE = "scrim_creation"
PARIS_TZ = ZoneInfo("Europe/Paris")
SCRIM_DATE_FORMAT = "%d/%m/%Y %H:%M"


@dataclass(frozen=True, slots=True)
class ScrimCreationData:
    scheduled_at: datetime
    map_name: str
    rank_name: str
    notes: str | None


class ScrimService:
    def __init__(
        self,
        scrims_db_service: ScrimsDbService,
        persistent_messages_service: PersistentMessagesService,
        rules_service,
    ) -> None:
        self._scrims = scrims_db_service
        self._messages = persistent_messages_service
        self._rules = rules_service

    async def has_accepted_rules(self, *, guild_id: int, discord_user_id: int) -> bool:
        return await self._rules.has_accepted_rules(guild_id=guild_id, discord_user_id=discord_user_id)

    async def create_scrim(
        self,
        *,
        guild_id: int,
        guild_name: str | None,
        creator_discord_id: int,
        data: ScrimCreationData,
    ) -> ScrimInfo:
        return await self._scrims.create_scrim(
            guild_id=guild_id,
            guild_name=guild_name,
            creator_discord_id=creator_discord_id,
            scheduled_at=data.scheduled_at,
            map_name=data.map_name,
            rank_name=data.rank_name,
            notes=data.notes,
        )

    async def save_scrim_message(self, *, scrim_id: int, channel_id: int, message_id: int) -> ScrimInfo | None:
        return await self._scrims.save_message(scrim_id=scrim_id, channel_id=channel_id, message_id=message_id)

    async def get_scrim(self, scrim_id: int) -> ScrimInfo | None:
        return await self._scrims.get_scrim(scrim_id)

    async def list_active_scrims(self, guild_id: int | None = None) -> tuple[ScrimInfo, ...]:
        return await self._scrims.list_active_scrims(guild_id)

    async def list_due_scrims(self, *, now: datetime) -> tuple[ScrimInfo, ...]:
        return await self._scrims.list_due_scrims(now=now)

    async def join_team(
        self,
        *,
        guild_id: int,
        guild_name: str | None,
        scrim_id: int,
        discord_user_id: int,
        team: str,
    ) -> ScrimJoinResult:
        if team not in {"team1", "team2"}:
            return ScrimJoinResult(status="not_found")
        return await self._scrims.join_team(
            guild_id=guild_id,
            guild_name=guild_name,
            scrim_id=scrim_id,
            discord_user_id=discord_user_id,
            team=team,
        )

    async def leave_scrim(self, *, guild_id: int, scrim_id: int, discord_user_id: int) -> ScrimLeaveResult:
        return await self._scrims.leave_scrim(
            guild_id=guild_id,
            scrim_id=scrim_id,
            discord_user_id=discord_user_id,
        )

    async def mark_completed(self, scrim_id: int) -> bool:
        return await self._scrims.mark_completed(scrim_id)

    async def save_creation_message(
        self,
        *,
        guild_id: int,
        guild_name: str | None,
        channel_id: int,
        message_id: int,
    ) -> None:
        await self._messages.save(
            guild_id=guild_id,
            guild_name=guild_name,
            message_type=SCRIM_CREATION_MESSAGE_TYPE,
            channel_id=channel_id,
            message_id=message_id,
        )

    async def get_creation_message(self, guild_id: int) -> PersistentMessageInfo | None:
        return await self._messages.get(guild_id, SCRIM_CREATION_MESSAGE_TYPE)

    @staticmethod
    def parse_creation_data(
        *,
        date_raw: str,
        time_raw: str,
        map_name: str,
        rank_name: str,
        notes: str,
    ) -> ScrimCreationData:
        scheduled_at = datetime.strptime(
            f"{date_raw.strip()} {time_raw.strip()}",
            SCRIM_DATE_FORMAT,
        ).replace(tzinfo=PARIS_TZ)
        clean_map = " ".join(map_name.strip().split())
        clean_rank = " ".join(rank_name.strip().split())
        clean_notes = " ".join(notes.strip().split()) if notes.strip() else None
        if not clean_map or not clean_rank:
            raise ValueError("empty")
        return ScrimCreationData(
            scheduled_at=scheduled_at,
            map_name=clean_map,
            rank_name=clean_rank,
            notes=clean_notes,
        )
