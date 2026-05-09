from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional

from database.repos.guild_member_repo import GuildMemberRepo
from database.repos.guilds_repo import GuildsRepo
from database.repos.scrims_repo import ScrimRow, ScrimsRepo
from database.repos.user_repo import UserRepo

SCRIM_TEAM_SIZE = 5

ScrimJoinStatus = Literal["joined", "already_registered", "full", "not_found"]
ScrimLeaveStatus = Literal["left", "not_registered", "not_found"]


@dataclass(frozen=True, slots=True)
class ScrimInfo:
    id: int
    guild_id: int
    creator_discord_id: Optional[int]
    scheduled_at: datetime
    map_name: str
    rank_name: str
    notes: Optional[str]
    team1_discord_ids: tuple[int, ...]
    team2_discord_ids: tuple[int, ...]
    channel_id: Optional[int]
    message_id: Optional[int]
    status: str

    @property
    def participant_discord_ids(self) -> tuple[int, ...]:
        return self.team1_discord_ids + self.team2_discord_ids


@dataclass(frozen=True, slots=True)
class ScrimJoinResult:
    status: ScrimJoinStatus
    scrim: Optional[ScrimInfo] = None


@dataclass(frozen=True, slots=True)
class ScrimLeaveResult:
    status: ScrimLeaveStatus
    scrim: Optional[ScrimInfo] = None


class ScrimsDbService:
    def __init__(self, db) -> None:
        self._db = db

    async def create_scrim(
        self,
        *,
        guild_id: int,
        guild_name: str | None,
        creator_discord_id: int,
        scheduled_at: datetime,
        map_name: str,
        rank_name: str,
        notes: str | None,
    ) -> ScrimInfo:
        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            creator_user_id = await UserRepo.ensure_exists(conn, discord_id=creator_discord_id)
            await GuildMemberRepo.mark_join(conn, guild_id=guild_id, user_id=creator_user_id)
            row = await ScrimsRepo.create(
                conn,
                guild_id=guild_id,
                creator_user_id=creator_user_id,
                scheduled_at=scheduled_at,
                map_name=map_name,
                rank_name=rank_name,
                notes=notes,
            )
            return await self._row_to_info(conn, row)

    async def save_message(self, *, scrim_id: int, channel_id: int, message_id: int) -> Optional[ScrimInfo]:
        async with self._db.transaction() as conn:
            row = await ScrimsRepo.set_message(
                conn,
                scrim_id=scrim_id,
                channel_id=channel_id,
                message_id=message_id,
            )
            return await self._row_to_info(conn, row) if row else None

    async def get_scrim(self, scrim_id: int) -> Optional[ScrimInfo]:
        async with self._db.acquire() as conn:
            row = await ScrimsRepo.get_by_id(conn, scrim_id)
            return await self._row_to_info(conn, row) if row else None

    async def list_active_scrims(self, guild_id: int | None = None) -> tuple[ScrimInfo, ...]:
        async with self._db.acquire() as conn:
            rows = await ScrimsRepo.list_active(conn, guild_id=guild_id)
            return tuple([await self._row_to_info(conn, row) for row in rows])

    async def list_due_scrims(self, *, now: datetime) -> tuple[ScrimInfo, ...]:
        async with self._db.acquire() as conn:
            rows = await ScrimsRepo.list_due(conn, now=now)
            return tuple([await self._row_to_info(conn, row) for row in rows])

    async def join_team(
        self,
        *,
        guild_id: int,
        guild_name: str | None,
        scrim_id: int,
        discord_user_id: int,
        team: str,
    ) -> ScrimJoinResult:
        async with self._db.transaction() as conn:
            row = await ScrimsRepo.get_by_id(conn, scrim_id)
            if row is None or row.guild_id != guild_id or row.status != "active":
                return ScrimJoinResult(status="not_found")

            user_id = await UserRepo.ensure_exists(conn, discord_id=discord_user_id)
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            await GuildMemberRepo.mark_join(conn, guild_id=guild_id, user_id=user_id)

            if user_id in row.team1_user_ids or user_id in row.team2_user_ids:
                return ScrimJoinResult(status="already_registered", scrim=await self._row_to_info(conn, row))

            target_team = row.team1_user_ids if team == "team1" else row.team2_user_ids
            if len(target_team) >= SCRIM_TEAM_SIZE:
                return ScrimJoinResult(status="full", scrim=await self._row_to_info(conn, row))

            updated = await ScrimsRepo.add_to_team(conn, scrim_id=scrim_id, user_id=user_id, team=team)
            if updated is None:
                return ScrimJoinResult(status="not_found")
            return ScrimJoinResult(status="joined", scrim=await self._row_to_info(conn, updated))

    async def leave_scrim(
        self,
        *,
        guild_id: int,
        scrim_id: int,
        discord_user_id: int,
    ) -> ScrimLeaveResult:
        async with self._db.transaction() as conn:
            row = await ScrimsRepo.get_by_id(conn, scrim_id)
            if row is None or row.guild_id != guild_id or row.status != "active":
                return ScrimLeaveResult(status="not_found")

            user_id = await UserRepo.get_user_id(conn, discord_user_id)
            if user_id is None or (user_id not in row.team1_user_ids and user_id not in row.team2_user_ids):
                return ScrimLeaveResult(status="not_registered", scrim=await self._row_to_info(conn, row))

            updated = await ScrimsRepo.remove_participant(conn, scrim_id=scrim_id, user_id=user_id)
            if updated is None:
                return ScrimLeaveResult(status="not_found")
            return ScrimLeaveResult(status="left", scrim=await self._row_to_info(conn, updated))

    async def mark_completed(self, scrim_id: int) -> bool:
        async with self._db.transaction() as conn:
            return await ScrimsRepo.mark_completed(conn, scrim_id=scrim_id)

    async def _row_to_info(self, conn, row: ScrimRow) -> ScrimInfo:
        user_ids = set(row.team1_user_ids) | set(row.team2_user_ids)
        if row.creator_user_id is not None:
            user_ids.add(row.creator_user_id)
        discord_ids = await UserRepo.get_discord_ids_by_user_ids(conn, list(user_ids))

        return ScrimInfo(
            id=row.id,
            guild_id=row.guild_id,
            creator_discord_id=discord_ids.get(row.creator_user_id) if row.creator_user_id is not None else None,
            scheduled_at=row.scheduled_at,
            map_name=row.map_name,
            rank_name=row.rank_name,
            notes=row.notes,
            team1_discord_ids=tuple(discord_ids[user_id] for user_id in row.team1_user_ids if user_id in discord_ids),
            team2_discord_ids=tuple(discord_ids[user_id] for user_id in row.team2_user_ids if user_id in discord_ids),
            channel_id=row.channel_id,
            message_id=row.message_id,
            status=row.status,
        )
