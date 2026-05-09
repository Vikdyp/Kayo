from __future__ import annotations

import random
import string
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Sequence

from database.services.five_stack_service import FiveStackDbService, FiveStackTeamInfo
from database.services.guild_channels_service import ChannelConfigurationService
from database.services.guild_roles_service import RoleConfigurationService
from database.services.persistent_messages_service import PersistentMessageInfo, PersistentMessagesService
from database.services.valorant_db_service import ValorantDbService

QUEUE_MESSAGE_TYPE = "queue_status"
TEAM_FORUM_CHANNEL_KEY = "teams_forum_id"
MATCHMAKING_CATEGORY_KEY = "matchmaking_voice_category"
VOICE_CLEANER_CATEGORY_KEY = "voice_cleaner_category"
VOICE_CLEANER_AFK_KEY = "voice_cleaner_afk"

GAME_ROLE_KEYS = ("duelist", "controller", "initiator", "sentinel", "fill")
LANGUAGE_ROLE_KEYS = ("francais", "anglais", "espagnol")
PLATFORM_ROLE_KEYS = ("pc", "console")
DEFAULT_LANGUAGE = "francais"
DEFAULT_REGION = "eu"
DEFAULT_PLATFORM = "pc"
DEFAULT_ELO = 1000
MAX_TEAM_MEMBERS = 5


@dataclass(frozen=True, slots=True)
class PlayerProfile:
    discord_id: int
    region: str
    platform: str
    rank: str | None
    elo: int | None

    @property
    def matchmaking_elo(self) -> int:
        return self.elo if self.elo is not None else DEFAULT_ELO


@dataclass(frozen=True, slots=True)
class QueueEntryData:
    guild_id: int
    guild_name: str | None
    discord_member_id: int
    entry_type: int
    team_code: str | None
    team_member_ids: tuple[int, ...]
    language: str
    region: str
    platform: str
    desired_team_size: int
    mmr_extended: bool
    elo: int | None
    elo_high: int | None
    elo_low: int | None
    roles: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TeamCreateResult:
    status: str
    team: FiveStackTeamInfo | None = None


@dataclass(frozen=True, slots=True)
class TeamMemberResult:
    status: str
    team: FiveStackTeamInfo | None = None


@dataclass(frozen=True, slots=True)
class MatchProposal:
    guild_id: int
    entries: tuple[object, ...]
    member_ids: tuple[int, ...]
    team_size: int
    quality_score: float
    elo_spread: int
    avg_elo: int
    role_diversity_score: float


class FiveStackService:
    def __init__(
        self,
        five_stack_db_service: FiveStackDbService,
        channel_config_service: ChannelConfigurationService,
        role_config_service: RoleConfigurationService,
        persistent_messages_service: PersistentMessagesService,
        valorant_db_service: ValorantDbService,
    ) -> None:
        self._db = five_stack_db_service
        self._channels = channel_config_service
        self._roles = role_config_service
        self._messages = persistent_messages_service
        self._valorant = valorant_db_service

    async def create_team(
        self,
        *,
        guild_id: int,
        guild_name: str | None,
        leader_discord_id: int,
        visibility: str,
    ) -> TeamCreateResult:
        if visibility not in {"public", "private"}:
            return TeamCreateResult(status="invalid_visibility")
        if await self._db.get_user_team(guild_id=guild_id, discord_member_id=leader_discord_id):
            return TeamCreateResult(status="already_in_team")
        if await self.get_player_profile(leader_discord_id) is None:
            return TeamCreateResult(status="missing_valorant")

        for _ in range(20):
            code = self.generate_team_code()
            try:
                team = await self._db.create_team(
                    guild_id=guild_id,
                    guild_name=guild_name,
                    code=code,
                    leader_discord_id=leader_discord_id,
                    visibility=visibility,
                )
                return TeamCreateResult(status="created", team=team)
            except Exception:
                if await self._db.get_team(guild_id=guild_id, code=code):
                    continue
                raise
        return TeamCreateResult(status="code_collision")

    async def join_team(
        self,
        *,
        guild_id: int,
        guild_name: str | None,
        code: str,
        discord_member_id: int,
    ) -> TeamMemberResult:
        team = await self._db.get_team(guild_id=guild_id, code=code)
        if team is None:
            return TeamMemberResult(status="not_found")
        if discord_member_id in team.member_ids:
            return TeamMemberResult(status="already_in_team", team=team)
        if await self._db.get_user_team(guild_id=guild_id, discord_member_id=discord_member_id):
            return TeamMemberResult(status="already_in_other_team", team=team)
        if len(team.member_ids) >= MAX_TEAM_MEMBERS:
            return TeamMemberResult(status="full", team=team)
        if await self.get_player_profile(discord_member_id) is None:
            return TeamMemberResult(status="missing_valorant", team=team)

        updated = await self._db.add_team_member(
            guild_id=guild_id,
            guild_name=guild_name,
            code=team.team.code,
            discord_member_id=discord_member_id,
        )
        return TeamMemberResult(status="joined", team=updated or team)

    async def leave_team(self, *, guild_id: int, discord_member_id: int) -> TeamMemberResult:
        team = await self._db.get_user_team(guild_id=guild_id, discord_member_id=discord_member_id)
        if team is None:
            return TeamMemberResult(status="not_in_team")
        updated = await self._db.remove_team_member(
            guild_id=guild_id,
            code=team.team.code,
            discord_member_id=discord_member_id,
        )
        return TeamMemberResult(status="left", team=updated)

    async def kick_member(
        self,
        *,
        guild_id: int,
        code: str,
        actor_discord_id: int,
        target_discord_id: int,
    ) -> TeamMemberResult:
        team = await self._db.get_team(guild_id=guild_id, code=code)
        if team is None:
            return TeamMemberResult(status="not_found")
        if actor_discord_id != team.team.leader_discord_id:
            return TeamMemberResult(status="not_leader", team=team)
        if target_discord_id == actor_discord_id:
            return TeamMemberResult(status="cannot_kick_self", team=team)
        if target_discord_id not in team.member_ids:
            return TeamMemberResult(status="member_not_in_team", team=team)
        updated = await self._db.remove_team_member(
            guild_id=guild_id,
            code=team.team.code,
            discord_member_id=target_discord_id,
        )
        return TeamMemberResult(status="kicked", team=updated)

    async def delete_team(self, *, guild_id: int, code: str, actor_discord_id: int) -> TeamMemberResult:
        team = await self._db.get_team(guild_id=guild_id, code=code)
        if team is None:
            return TeamMemberResult(status="not_found")
        if actor_discord_id != team.team.leader_discord_id:
            return TeamMemberResult(status="not_leader", team=team)
        await self._db.delete_team(guild_id=guild_id, code=team.team.code)
        return TeamMemberResult(status="deleted", team=team)

    async def get_team(self, *, guild_id: int, code: str) -> FiveStackTeamInfo | None:
        return await self._db.get_team(guild_id=guild_id, code=code)

    async def get_user_team(self, *, guild_id: int, discord_member_id: int) -> FiveStackTeamInfo | None:
        return await self._db.get_user_team(guild_id=guild_id, discord_member_id=discord_member_id)

    async def list_teams(self, guild_id: int) -> tuple[FiveStackTeamInfo, ...]:
        return await self._db.list_teams(guild_id)

    async def set_team_thread(
        self,
        *,
        guild_id: int,
        code: str,
        forum_channel_id: int | None,
        thread_id: int | None,
    ) -> bool:
        return await self._db.set_team_thread(
            guild_id=guild_id,
            code=code,
            forum_channel_id=forum_channel_id,
            thread_id=thread_id,
        )

    async def set_team_voice_channel(self, *, guild_id: int, code: str, voice_channel_id: int | None) -> bool:
        return await self._db.set_team_voice_channel(
            guild_id=guild_id,
            code=code,
            voice_channel_id=voice_channel_id,
        )

    async def list_old_teams(self, *, hours: int) -> tuple[FiveStackTeamInfo, ...]:
        return await self._db.list_old_teams(hours=hours)

    async def build_solo_queue_data(
        self,
        *,
        guild_id: int,
        guild_name: str | None,
        member_id: int,
        role_ids: set[int],
        desired_team_size: int,
    ) -> QueueEntryData | None:
        profile = await self.get_player_profile(member_id)
        if profile is None:
            return None
        language = await self.detect_language(guild_id, role_ids)
        roles = await self.detect_game_roles(guild_id, role_ids)
        return QueueEntryData(
            guild_id=guild_id,
            guild_name=guild_name,
            discord_member_id=member_id,
            entry_type=1,
            team_code=None,
            team_member_ids=(member_id,),
            language=language,
            region=profile.region,
            platform=profile.platform,
            desired_team_size=desired_team_size,
            mmr_extended=False,
            elo=profile.elo,
            elo_high=profile.matchmaking_elo + 150,
            elo_low=max(0, profile.matchmaking_elo - 150),
            roles=roles,
        )

    async def build_team_queue_data(
        self,
        *,
        guild_id: int,
        guild_name: str | None,
        leader_id: int,
        leader_role_ids: set[int],
        desired_team_size: int,
    ) -> QueueEntryData | None:
        team = await self._db.get_user_team(guild_id=guild_id, discord_member_id=leader_id)
        if team is None or team.team.leader_discord_id != leader_id:
            return None

        profiles = []
        for member_id in team.member_ids:
            profile = await self.get_player_profile(member_id)
            if profile is None:
                return None
            profiles.append(profile)

        first = profiles[0]
        elos = [profile.matchmaking_elo for profile in profiles]
        language = await self.detect_language(guild_id, leader_role_ids)
        roles = await self.detect_game_roles(guild_id, leader_role_ids)
        return QueueEntryData(
            guild_id=guild_id,
            guild_name=guild_name,
            discord_member_id=leader_id,
            entry_type=len(team.member_ids),
            team_code=team.team.code,
            team_member_ids=team.member_ids,
            language=language,
            region=first.region,
            platform=first.platform,
            desired_team_size=desired_team_size,
            mmr_extended=False,
            elo=sum(elos) // len(elos),
            elo_high=max(elos),
            elo_low=min(elos),
            roles=roles,
        )

    async def add_queue_entry(self, data: QueueEntryData):
        return await self._db.add_queue_entry(
            guild_id=data.guild_id,
            guild_name=data.guild_name,
            discord_member_id=data.discord_member_id,
            entry_type=data.entry_type,
            team_code=data.team_code,
            team_member_ids=data.team_member_ids,
            language=data.language,
            region=data.region,
            platform=data.platform,
            desired_team_size=data.desired_team_size,
            mmr_extended=data.mmr_extended,
            elo=data.elo,
            elo_high=data.elo_high,
            elo_low=data.elo_low,
            roles=data.roles,
        )

    async def remove_from_queue(self, *, guild_id: int, discord_member_id: int) -> bool:
        return await self._db.remove_from_queue(guild_id=guild_id, discord_member_id=discord_member_id)

    async def list_queue(self, guild_id: int | None = None):
        return await self._db.list_queue(guild_id)

    async def cleanup_queue(self, *, any_after_seconds: int = 300, remove_after_seconds: int = 600):
        return await self._db.cleanup_queue(
            any_after_seconds=any_after_seconds,
            remove_after_seconds=remove_after_seconds,
        )

    async def find_match_proposals(self, guild_id: int | None = None) -> tuple[MatchProposal, ...]:
        entries = await self._db.list_queue(guild_id)
        proposals = []
        used_entry_ids: set[int] = set()

        for candidate_group in self._compatible_groups(entries):
            available = [entry for entry in candidate_group if entry.id not in used_entry_ids]
            for target_size in (5, 3, 2):
                proposal = self._build_greedy_proposal(available, target_size)
                if proposal is None:
                    continue
                proposals.append(proposal)
                used_entry_ids.update(entry.id for entry in proposal.entries)
                break

        return tuple(proposals)

    async def record_match(self, proposal: MatchProposal, *, match_code: str, voice_channel_id: int | None):
        return await self._db.create_match(
            guild_id=proposal.guild_id,
            match_code=match_code,
            voice_channel_id=voice_channel_id,
            entries=proposal.entries,
            team_size=proposal.team_size,
            quality_score=proposal.quality_score,
            elo_spread=proposal.elo_spread,
            avg_elo=proposal.avg_elo,
            role_diversity_score=proposal.role_diversity_score,
        )

    async def get_player_stats(self, *, guild_id: int, discord_member_id: int):
        return await self._db.get_player_stats(guild_id=guild_id, discord_member_id=discord_member_id)

    async def get_server_stats(self, guild_id: int) -> dict:
        return await self._db.get_server_stats(guild_id)

    async def get_leaderboard(self, *, guild_id: int, category: str, limit: int):
        return await self._db.get_leaderboard(guild_id=guild_id, category=category, limit=limit)

    async def get_match_history(self, *, guild_id: int, limit: int):
        return await self._db.get_match_history(guild_id=guild_id, limit=limit)

    async def get_player_match_history(self, *, guild_id: int, discord_member_id: int, limit: int):
        return await self._db.get_player_match_history(
            guild_id=guild_id,
            discord_member_id=discord_member_id,
            limit=limit,
        )

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
        await self._db.save_feedback(
            match_id=match_id,
            reporter_id=reporter_id,
            rating=rating,
            feedback_type=feedback_type,
            issues=issues,
            comment=comment,
        )

    async def get_team_forum_channel_id(self, guild_id: int) -> int | None:
        return await self._channels.get_one(guild_id, TEAM_FORUM_CHANNEL_KEY)

    async def get_matchmaking_category_id(self, guild_id: int) -> int | None:
        return await self._channels.get_one(guild_id, MATCHMAKING_CATEGORY_KEY)

    async def get_voice_cleaner_category_id(self, guild_id: int) -> int | None:
        return await self._channels.get_one(guild_id, VOICE_CLEANER_CATEGORY_KEY)

    async def get_voice_cleaner_afk_id(self, guild_id: int) -> int | None:
        return await self._channels.get_one(guild_id, VOICE_CLEANER_AFK_KEY)

    async def save_queue_message(
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
            message_type=QUEUE_MESSAGE_TYPE,
            channel_id=channel_id,
            message_id=message_id,
        )

    async def get_queue_message(self, guild_id: int) -> PersistentMessageInfo | None:
        return await self._messages.get(guild_id, QUEUE_MESSAGE_TYPE)

    async def get_player_profile(self, discord_id: int) -> PlayerProfile | None:
        info = await self._valorant.get_valorant_info_by_discord_id(discord_id)
        if info is None:
            return None
        return PlayerProfile(
            discord_id=discord_id,
            region=(info.region or DEFAULT_REGION).lower(),
            platform=(info.platform or DEFAULT_PLATFORM).lower(),
            rank=info.rank,
            elo=info.elo,
        )

    async def detect_game_roles(self, guild_id: int, member_role_ids: set[int]) -> tuple[str, ...]:
        configured = await self._roles.get_all(guild_id)
        selected = tuple(key for key in GAME_ROLE_KEYS if configured.get(key) in member_role_ids)
        return selected or ("fill",)

    async def detect_language(self, guild_id: int, member_role_ids: set[int]) -> str:
        configured = await self._roles.get_all(guild_id)
        for key in LANGUAGE_ROLE_KEYS:
            if configured.get(key) in member_role_ids:
                return key
        return DEFAULT_LANGUAGE

    @staticmethod
    def generate_team_code(length: int = 6) -> str:
        return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))

    @staticmethod
    def generate_match_code(length: int = 6) -> str:
        return "M" + "".join(random.choices(string.ascii_uppercase + string.digits, k=length))

    @staticmethod
    def role_counts(entries: Iterable[object]) -> dict[str, int]:
        counts = {key: 0 for key in GAME_ROLE_KEYS}
        for entry in entries:
            for role in getattr(entry, "roles", ()) or ("fill",):
                if role in counts:
                    counts[role] += len(getattr(entry, "all_member_ids", ()))
        return counts

    def _compatible_groups(self, entries: Sequence[object]) -> list[list[object]]:
        groups: dict[tuple[int, str, str, str], list[object]] = {}
        for entry in entries:
            key = (entry.guild_id, entry.language, entry.region, entry.platform)
            groups.setdefault(key, []).append(entry)
        return [sorted(group, key=lambda item: item.queued_at) for group in groups.values()]

    def _build_greedy_proposal(self, entries: Sequence[object], target_size: int) -> MatchProposal | None:
        candidates = [
            entry
            for entry in entries
            if entry.entry_type <= target_size
            and entry.desired_team_size in {0, target_size}
        ]
        selected = []
        member_ids: list[int] = []
        total = 0

        for entry in candidates:
            entry_members = list(entry.all_member_ids)
            if total + len(entry_members) > target_size:
                continue
            if set(entry_members) & set(member_ids):
                continue
            selected.append(entry)
            member_ids.extend(entry_members)
            total += len(entry_members)
            if total == target_size:
                break

        if total != target_size or not selected:
            return None

        elos = [entry.elo if entry.elo is not None else DEFAULT_ELO for entry in selected]
        elo_spread = max(elos) - min(elos) if len(elos) > 1 else 0
        avg_elo = sum(elos) // len(elos)
        roles = {role for entry in selected for role in entry.roles}
        role_diversity = min(1.0, len(roles) / 5)
        wait_bonus = min(0.2, self._oldest_wait_seconds(selected) / 1800)
        quality_score = max(0.0, min(1.0, 1 - (elo_spread / 1000) + role_diversity * 0.2 + wait_bonus))

        return MatchProposal(
            guild_id=selected[0].guild_id,
            entries=tuple(selected),
            member_ids=tuple(member_ids),
            team_size=target_size,
            quality_score=round(quality_score, 3),
            elo_spread=elo_spread,
            avg_elo=avg_elo,
            role_diversity_score=round(role_diversity, 3),
        )

    @staticmethod
    def _oldest_wait_seconds(entries: Sequence[object]) -> int:
        now = datetime.now(timezone.utc)
        waits = []
        for entry in entries:
            queued_at = entry.queued_at if entry.queued_at.tzinfo else entry.queued_at.replace(tzinfo=timezone.utc)
            waits.append(max(0, int((now - queued_at).total_seconds())))
        return max(waits) if waits else 0
