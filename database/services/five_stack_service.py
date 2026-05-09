from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from database.repos.five_stack_feedback_repo import FiveStackFeedbackRepo
from database.repos.five_stack_match_participants_repo import FiveStackMatchParticipantRow, FiveStackMatchParticipantsRepo
from database.repos.five_stack_matches_repo import FiveStackMatchRow, FiveStackMatchesRepo
from database.repos.five_stack_player_stats_repo import FiveStackPlayerStatsRepo, FiveStackPlayerStatsRow
from database.repos.five_stack_queue_repo import FiveStackQueueRepo, FiveStackQueueRow
from database.repos.five_stack_team_members_repo import FiveStackTeamMembersRepo
from database.repos.five_stack_teams_repo import FiveStackTeamRow, FiveStackTeamsRepo
from database.repos.guild_member_repo import GuildMemberRepo
from database.repos.guilds_repo import GuildsRepo
from database.repos.user_repo import UserRepo


@dataclass(frozen=True, slots=True)
class FiveStackTeamInfo:
    team: FiveStackTeamRow
    member_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class FiveStackMatchBundle:
    match: FiveStackMatchRow
    participants: tuple[FiveStackMatchParticipantRow, ...]


class FiveStackDbService:
    def __init__(self, db) -> None:
        self._db = db

    async def create_team(
        self,
        *,
        guild_id: int,
        guild_name: str | None,
        code: str,
        leader_discord_id: int,
        visibility: str,
        forum_channel_id: int | None = None,
        thread_id: int | None = None,
    ) -> FiveStackTeamInfo:
        async with self._db.transaction() as conn:
            await self._ensure_member(conn, guild_id=guild_id, guild_name=guild_name, discord_id=leader_discord_id)
            team = await FiveStackTeamsRepo.create(
                conn,
                guild_id=guild_id,
                code=code,
                leader_discord_id=leader_discord_id,
                visibility=visibility,
                forum_channel_id=forum_channel_id,
                thread_id=thread_id,
            )
            await FiveStackTeamMembersRepo.insert(
                conn,
                guild_id=guild_id,
                team_code=code,
                member_discord_id=leader_discord_id,
            )
            return FiveStackTeamInfo(team=team, member_ids=(leader_discord_id,))

    async def get_team(self, *, guild_id: int, code: str) -> FiveStackTeamInfo | None:
        async with self._db.acquire() as conn:
            team = await FiveStackTeamsRepo.get(conn, guild_id=guild_id, code=code.upper())
            if team is None:
                return None
            members = await FiveStackTeamMembersRepo.list_by_team(conn, guild_id=guild_id, team_code=team.code)
            return FiveStackTeamInfo(team=team, member_ids=tuple(row.member_discord_id for row in members))

    async def get_user_team(self, *, guild_id: int, discord_member_id: int) -> FiveStackTeamInfo | None:
        async with self._db.acquire() as conn:
            membership = await FiveStackTeamMembersRepo.get_user_membership(
                conn,
                guild_id=guild_id,
                member_discord_id=discord_member_id,
            )
            if membership is None:
                return None
            team = await FiveStackTeamsRepo.get(conn, guild_id=guild_id, code=membership.team_code)
            if team is None:
                return None
            members = await FiveStackTeamMembersRepo.list_by_team(conn, guild_id=guild_id, team_code=team.code)
            return FiveStackTeamInfo(team=team, member_ids=tuple(row.member_discord_id for row in members))

    async def list_teams(self, guild_id: int) -> tuple[FiveStackTeamInfo, ...]:
        async with self._db.acquire() as conn:
            teams = await FiveStackTeamsRepo.list_active(conn, guild_id)
            result = []
            for team in teams:
                members = await FiveStackTeamMembersRepo.list_by_team(conn, guild_id=guild_id, team_code=team.code)
                result.append(FiveStackTeamInfo(team=team, member_ids=tuple(row.member_discord_id for row in members)))
            return tuple(result)

    async def add_team_member(
        self,
        *,
        guild_id: int,
        guild_name: str | None,
        code: str,
        discord_member_id: int,
    ) -> FiveStackTeamInfo | None:
        async with self._db.transaction() as conn:
            team = await FiveStackTeamsRepo.get(conn, guild_id=guild_id, code=code.upper())
            if team is None:
                return None
            await self._ensure_member(conn, guild_id=guild_id, guild_name=guild_name, discord_id=discord_member_id)
            await FiveStackTeamMembersRepo.insert(
                conn,
                guild_id=guild_id,
                team_code=team.code,
                member_discord_id=discord_member_id,
            )
            members = await FiveStackTeamMembersRepo.list_by_team(conn, guild_id=guild_id, team_code=team.code)
            return FiveStackTeamInfo(team=team, member_ids=tuple(row.member_discord_id for row in members))

    async def remove_team_member(
        self,
        *,
        guild_id: int,
        code: str,
        discord_member_id: int,
    ) -> FiveStackTeamInfo | None:
        async with self._db.transaction() as conn:
            team = await FiveStackTeamsRepo.get(conn, guild_id=guild_id, code=code.upper())
            if team is None:
                return None
            await FiveStackTeamMembersRepo.delete(
                conn,
                guild_id=guild_id,
                team_code=team.code,
                member_discord_id=discord_member_id,
            )
            members = await FiveStackTeamMembersRepo.list_by_team(conn, guild_id=guild_id, team_code=team.code)
            member_ids = tuple(row.member_discord_id for row in members)
            if not member_ids:
                await FiveStackTeamsRepo.mark_deleted(conn, guild_id=guild_id, code=team.code)
            elif team.leader_discord_id == discord_member_id:
                await FiveStackTeamsRepo.update_leader(
                    conn,
                    guild_id=guild_id,
                    code=team.code,
                    leader_discord_id=member_ids[0],
                )
                team = await FiveStackTeamsRepo.get(conn, guild_id=guild_id, code=team.code) or team
            return FiveStackTeamInfo(team=team, member_ids=member_ids)

    async def delete_team(self, *, guild_id: int, code: str) -> bool:
        async with self._db.transaction() as conn:
            await FiveStackTeamMembersRepo.delete_team(conn, guild_id=guild_id, team_code=code.upper())
            return await FiveStackTeamsRepo.mark_deleted(conn, guild_id=guild_id, code=code.upper())

    async def set_team_thread(
        self,
        *,
        guild_id: int,
        code: str,
        forum_channel_id: int | None,
        thread_id: int | None,
    ) -> bool:
        async with self._db.transaction() as conn:
            return await FiveStackTeamsRepo.set_thread(
                conn,
                guild_id=guild_id,
                code=code.upper(),
                forum_channel_id=forum_channel_id,
                thread_id=thread_id,
            )

    async def set_team_voice_channel(self, *, guild_id: int, code: str, voice_channel_id: int | None) -> bool:
        async with self._db.transaction() as conn:
            return await FiveStackTeamsRepo.set_voice_channel(
                conn,
                guild_id=guild_id,
                code=code.upper(),
                voice_channel_id=voice_channel_id,
            )

    async def list_old_teams(self, *, hours: int) -> tuple[FiveStackTeamInfo, ...]:
        async with self._db.acquire() as conn:
            teams = await FiveStackTeamsRepo.list_older_than(conn, hours=hours)
            result = []
            for team in teams:
                members = await FiveStackTeamMembersRepo.list_by_team(conn, guild_id=team.guild_id, team_code=team.code)
                result.append(FiveStackTeamInfo(team=team, member_ids=tuple(row.member_discord_id for row in members)))
            return tuple(result)

    async def add_queue_entry(self, **kwargs) -> FiveStackQueueRow:
        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, kwargs["guild_id"], kwargs.get("guild_name"))
            for discord_id in kwargs["team_member_ids"] or (kwargs["discord_member_id"],):
                await self._ensure_member(conn, guild_id=kwargs["guild_id"], guild_name=kwargs.get("guild_name"), discord_id=discord_id)
            return await FiveStackQueueRepo.upsert(conn, **{k: v for k, v in kwargs.items() if k != "guild_name"})

    async def remove_from_queue(self, *, guild_id: int, discord_member_id: int) -> bool:
        async with self._db.transaction() as conn:
            return await FiveStackQueueRepo.delete_member(conn, guild_id=guild_id, discord_member_id=discord_member_id)

    async def list_queue(self, guild_id: int | None = None) -> tuple[FiveStackQueueRow, ...]:
        async with self._db.acquire() as conn:
            rows = await FiveStackQueueRepo.list_by_guild(conn, guild_id) if guild_id else await FiveStackQueueRepo.list_all(conn)
            return tuple(rows)

    async def cleanup_queue(self, *, any_after_seconds: int, remove_after_seconds: int) -> tuple[int, tuple[int, ...]]:
        async with self._db.transaction() as conn:
            converted = await FiveStackQueueRepo.convert_old_to_any(conn, older_than_seconds=any_after_seconds)
            removed = await FiveStackQueueRepo.delete_stale(conn, older_than_seconds=remove_after_seconds)
            return converted, tuple(removed)

    async def create_match(
        self,
        *,
        guild_id: int,
        match_code: str,
        voice_channel_id: int | None,
        entries: tuple[FiveStackQueueRow, ...],
        team_size: int,
        quality_score: float,
        elo_spread: int,
        avg_elo: int,
        role_diversity_score: float,
    ) -> FiveStackMatchRow:
        async with self._db.transaction() as conn:
            now = datetime.now(timezone.utc)
            total_wait = 0
            for entry in entries:
                queued_at = entry.queued_at if entry.queued_at.tzinfo else entry.queued_at.replace(tzinfo=timezone.utc)
                total_wait += max(0, int((now - queued_at).total_seconds()))

            first = entries[0]
            match = await FiveStackMatchesRepo.create(
                conn,
                guild_id=guild_id,
                match_code=match_code,
                voice_channel_id=voice_channel_id,
                quality_score=quality_score,
                elo_spread=elo_spread,
                avg_elo=avg_elo,
                role_diversity_score=role_diversity_score,
                total_wait_time_seconds=total_wait,
                team_size=team_size,
                language=first.language,
                region=first.region,
                platform=first.platform,
            )
            for entry in entries:
                wait = max(0, int((now - (entry.queued_at if entry.queued_at.tzinfo else entry.queued_at.replace(tzinfo=timezone.utc))).total_seconds()))
                for member_id in entry.all_member_ids:
                    await FiveStackMatchParticipantsRepo.insert(
                        conn,
                        match_id=match.id,
                        discord_member_id=member_id,
                        elo_at_match=entry.elo,
                        roles_selected=entry.roles,
                        entry_type=entry.entry_type,
                        wait_time_seconds=wait,
                    )
                    await FiveStackPlayerStatsRepo.upsert_after_match(
                        conn,
                        guild_id=guild_id,
                        discord_member_id=member_id,
                        wait_time_seconds=wait,
                        is_solo=entry.entry_type == 1,
                        preferred_role=entry.roles[0] if entry.roles else None,
                    )
            await FiveStackQueueRepo.delete_ids(conn, guild_id=guild_id, entry_ids=tuple(entry.id for entry in entries))
            return match

    async def get_player_stats(self, *, guild_id: int, discord_member_id: int) -> FiveStackPlayerStatsRow | None:
        async with self._db.acquire() as conn:
            return await FiveStackPlayerStatsRepo.get(conn, guild_id=guild_id, discord_member_id=discord_member_id)

    async def get_server_stats(self, guild_id: int) -> dict:
        async with self._db.acquire() as conn:
            stats = await FiveStackMatchesRepo.server_stats(conn, guild_id)
            stats["team_size_distribution"] = await FiveStackMatchesRepo.size_distribution(conn, guild_id)
            return stats

    async def get_leaderboard(self, *, guild_id: int, category: str, limit: int) -> tuple[FiveStackPlayerStatsRow, ...]:
        async with self._db.acquire() as conn:
            return tuple(await FiveStackPlayerStatsRepo.leaderboard(conn, guild_id=guild_id, order_by=category, limit=limit))

    async def get_match_history(self, *, guild_id: int, limit: int) -> tuple[FiveStackMatchRow, ...]:
        async with self._db.acquire() as conn:
            return tuple(await FiveStackMatchesRepo.list_by_guild(conn, guild_id=guild_id, limit=limit))

    async def get_player_match_history(
        self,
        *,
        guild_id: int,
        discord_member_id: int,
        limit: int,
    ) -> tuple[FiveStackMatchBundle, ...]:
        async with self._db.acquire() as conn:
            participants = await FiveStackMatchParticipantsRepo.list_by_member(conn, discord_member_id=discord_member_id, limit=limit)
            result = []
            for participant in participants:
                match = await FiveStackMatchesRepo.get_by_id(conn, participant.match_id)
                if match and match.guild_id == guild_id:
                    all_participants = await FiveStackMatchParticipantsRepo.list_by_match(conn, match.id)
                    result.append(FiveStackMatchBundle(match=match, participants=tuple(all_participants)))
            return tuple(result)

    async def save_feedback(
        self,
        *,
        match_id: int,
        reporter_id: int,
        rating: int,
        feedback_type: str,
        issues: tuple[str, ...] = (),
        comment: str | None = None,
    ) -> None:
        async with self._db.transaction() as conn:
            await FiveStackFeedbackRepo.upsert(
                conn,
                match_id=match_id,
                reporter_id=reporter_id,
                rating=rating,
                feedback_type=feedback_type,
                issues=issues,
                comment=comment,
            )

    async def _ensure_member(self, conn, *, guild_id: int, guild_name: str | None, discord_id: int) -> int:
        await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
        user_id = await UserRepo.ensure_exists(conn, discord_id=discord_id)
        await GuildMemberRepo.mark_join(conn, guild_id=guild_id, user_id=user_id)
        return user_id
