from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal, Optional

from database.repos.guild_member_repo import GuildMemberRepo
from database.repos.guilds_repo import GuildsRepo
from database.repos.reputation_events_repo import ReputationEventsRepo, ReputationEventType
from database.repos.user_profiles_repo import UserProfilesRepo
from database.repos.user_repo import UserRepo

MAX_REPUTATION_EVENTS_PER_PAIR = 5

ReputationAddStatus = Literal["created", "duplicate_today", "limit_reached"]


@dataclass(frozen=True, slots=True)
class ReputationAddResult:
    status: ReputationAddStatus

    @property
    def created(self) -> bool:
        return self.status == "created"


@dataclass(frozen=True, slots=True)
class ReputationSummary:
    reports: int
    recommendations: int


@dataclass(frozen=True, slots=True)
class UserProfileInfo:
    genre: Optional[str] = None
    valorant_tracker: Optional[str] = None
    lft: Optional[str] = None
    note: Optional[str] = None


class ReputationDbService:
    def __init__(self, db) -> None:
        self._db = db

    async def add_event(
        self,
        *,
        guild_id: int,
        guild_name: str | None,
        reporter_discord_id: int,
        target_discord_id: int,
        event_type: ReputationEventType,
        reason: str | None,
        event_date: date | None = None,
    ) -> ReputationAddResult:
        event_date = event_date or date.today()
        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            reporter_user_id = await UserRepo.ensure_exists(conn, discord_id=reporter_discord_id)
            target_user_id = await UserRepo.ensure_exists(conn, discord_id=target_discord_id)
            await GuildMemberRepo.mark_join(conn, guild_id=guild_id, user_id=reporter_user_id)
            await GuildMemberRepo.mark_join(conn, guild_id=guild_id, user_id=target_user_id)

            today_count = await ReputationEventsRepo.count_for_pair(
                conn,
                guild_id=guild_id,
                reporter_user_id=reporter_user_id,
                target_user_id=target_user_id,
                event_type=event_type,
                event_date=event_date,
            )
            if today_count >= 1:
                return ReputationAddResult(status="duplicate_today")

            total_count = await ReputationEventsRepo.count_for_pair(
                conn,
                guild_id=guild_id,
                reporter_user_id=reporter_user_id,
                target_user_id=target_user_id,
                event_type=event_type,
            )
            if total_count >= MAX_REPUTATION_EVENTS_PER_PAIR:
                return ReputationAddResult(status="limit_reached")

            inserted = await ReputationEventsRepo.insert_event(
                conn,
                guild_id=guild_id,
                reporter_user_id=reporter_user_id,
                target_user_id=target_user_id,
                event_type=event_type,
                reason=reason,
                event_date=event_date,
            )
            return ReputationAddResult(status="created" if inserted else "duplicate_today")

    async def get_summary(self, *, guild_id: int, target_discord_id: int) -> ReputationSummary:
        async with self._db.transaction() as conn:
            target_user_id = await UserRepo.ensure_exists(conn, discord_id=target_discord_id)
            row = await ReputationEventsRepo.get_summary(
                conn,
                guild_id=guild_id,
                target_user_id=target_user_id,
            )
            return ReputationSummary(
                reports=row.reports,
                recommendations=row.recommendations,
            )

    async def get_profile(self, discord_id: int) -> UserProfileInfo:
        async with self._db.transaction() as conn:
            user_id = await UserRepo.ensure_exists(conn, discord_id=discord_id)
            row = await UserProfilesRepo.get(conn, user_id)
            if row is None:
                return UserProfileInfo()
            return UserProfileInfo(
                genre=row.genre,
                valorant_tracker=row.valorant_tracker,
                lft=row.lft,
                note=row.note,
            )

    async def save_profile(
        self,
        *,
        discord_id: int,
        genre: str | None,
        valorant_tracker: str | None,
        lft: str | None,
        note: str | None,
    ) -> UserProfileInfo:
        async with self._db.transaction() as conn:
            user_id = await UserRepo.ensure_exists(conn, discord_id=discord_id)
            await UserProfilesRepo.upsert(
                conn,
                user_id=user_id,
                genre=genre,
                valorant_tracker=valorant_tracker,
                lft=lft,
                note=note,
            )
            return UserProfileInfo(
                genre=genre,
                valorant_tracker=valorant_tracker,
                lft=lft,
                note=note,
            )
