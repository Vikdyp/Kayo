from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from database.services.guild_channels_service import ChannelConfigurationService
from database.services.guild_roles_service import RoleConfigurationService


RANK_UP_CHANNEL_KEY = "rank_up"
RANK_ORDER: Mapping[str, int] = {
    "radiant": 1,
    "immortel": 2,
    "ascendant": 3,
    "diamant": 4,
    "platine": 5,
    "or": 6,
    "argent": 7,
    "bronze": 8,
    "fer": 9,
}
RANK_NAMES = frozenset(RANK_ORDER)


@dataclass(frozen=True, slots=True)
class RankNotificationConfig:
    rank_roles: dict[str, int]
    log_channel_id: int | None

    @property
    def is_complete(self) -> bool:
        return bool(self.rank_roles) and self.log_channel_id is not None


@dataclass(frozen=True, slots=True)
class RankRoleDelta:
    removed: frozenset[str]
    added: frozenset[str]


class RankNotificationService:
    def __init__(
        self,
        role_config_service: RoleConfigurationService,
        channel_config_service: ChannelConfigurationService,
    ) -> None:
        self._roles = role_config_service
        self._channels = channel_config_service

    async def get_config(self, guild_id: int) -> RankNotificationConfig:
        roles = await self._roles.get_all(guild_id)
        rank_roles = {key: role_id for key, role_id in roles.items() if key in RANK_NAMES}
        log_channel_id = await self._channels.get_one(guild_id, RANK_UP_CHANNEL_KEY)
        return RankNotificationConfig(rank_roles=rank_roles, log_channel_id=log_channel_id)

    def analyze_role_delta(
        self,
        *,
        before_role_ids: Iterable[int],
        after_role_ids: Iterable[int],
        config: RankNotificationConfig,
    ) -> RankRoleDelta:
        before_rank_names = self.rank_names_for_role_ids(before_role_ids, config)
        after_rank_names = self.rank_names_for_role_ids(after_role_ids, config)
        return RankRoleDelta(
            removed=frozenset(before_rank_names - after_rank_names),
            added=frozenset(after_rank_names - before_rank_names),
        )

    def rank_names_for_role_ids(
        self,
        role_ids: Iterable[int],
        config: RankNotificationConfig,
    ) -> set[str]:
        role_id_set = set(role_ids)
        return {rank for rank, role_id in config.rank_roles.items() if role_id in role_id_set}

    def calculate_top_percentile(
        self,
        *,
        guild_member_role_ids: Iterable[Iterable[int]],
        new_rank: str,
        config: RankNotificationConfig,
    ) -> float:
        new_rank_value = RANK_ORDER.get(new_rank, 99)
        total_ranked = 0
        worse_count = 0

        for member_role_ids in guild_member_role_ids:
            member_ranks = self.rank_names_for_role_ids(member_role_ids, config)
            if not member_ranks:
                continue

            total_ranked += 1
            best_member_rank = min(RANK_ORDER.get(rank, 99) for rank in member_ranks)
            if best_member_rank > new_rank_value:
                worse_count += 1

        if total_ranked == 0:
            return 100.0
        return 100 - (worse_count / total_ranked) * 100
