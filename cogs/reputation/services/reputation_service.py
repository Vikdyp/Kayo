from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Mapping, Optional

from database.services.guild_roles_service import RoleConfigurationService
from database.services.reputation_service import (
    ReputationAddResult,
    ReputationDbService,
    ReputationSummary,
    UserProfileInfo,
)

GOOD_REPUTATION_ROLE_KEY = "bon joueur"
BAD_REPUTATION_ROLE_KEY = "mauvais joueur"
TRACKER_URL_PATTERN = re.compile(r"^https://tracker\.gg/valorant/profile/riot/.+/overview$")
URL_PATTERN = re.compile(r"https?://", re.IGNORECASE)
ReputationEventType = Literal["report", "recommendation"]


@dataclass(frozen=True, slots=True)
class ProfileSaveResult:
    success: bool
    profile: UserProfileInfo
    error: Optional[str] = None


@dataclass(frozen=True, slots=True)
class ReputationRolePlan:
    role_id_to_add: Optional[int]
    role_ids_to_remove: tuple[int, ...]


class ReputationService:
    def __init__(
        self,
        reputation_db_service: ReputationDbService,
        role_config_service: RoleConfigurationService,
    ) -> None:
        self._reputation = reputation_db_service
        self._roles = role_config_service

    async def add_event(
        self,
        *,
        guild_id: int,
        guild_name: str | None,
        reporter_discord_id: int,
        target_discord_id: int,
        event_type: ReputationEventType,
        reason: str | None,
    ) -> ReputationAddResult:
        return await self._reputation.add_event(
            guild_id=guild_id,
            guild_name=guild_name,
            reporter_discord_id=reporter_discord_id,
            target_discord_id=target_discord_id,
            event_type=event_type,
            reason=reason,
        )

    async def get_summary(self, *, guild_id: int, target_discord_id: int) -> ReputationSummary:
        return await self._reputation.get_summary(
            guild_id=guild_id,
            target_discord_id=target_discord_id,
        )

    async def get_profile(self, discord_id: int) -> UserProfileInfo:
        return await self._reputation.get_profile(discord_id)

    async def save_profile(
        self,
        *,
        discord_id: int,
        genre: str | None,
        valorant_tracker: str | None,
        lft: str | None,
        note: str | None,
    ) -> ProfileSaveResult:
        current_profile = await self.get_profile(discord_id)
        normalized_genre = self.normalize_genre(genre) if genre is not None else current_profile.genre
        tracker = valorant_tracker if valorant_tracker is not None else current_profile.valorant_tracker
        updated_lft = lft if lft is not None else current_profile.lft
        updated_note = note if note is not None else current_profile.note

        error = self.validate_profile_fields(
            genre=normalized_genre,
            valorant_tracker=tracker,
            note=updated_note,
        )
        if error:
            return ProfileSaveResult(success=False, profile=current_profile, error=error)

        profile = await self._reputation.save_profile(
            discord_id=discord_id,
            genre=normalized_genre,
            valorant_tracker=tracker,
            lft=updated_lft,
            note=updated_note,
        )
        return ProfileSaveResult(success=True, profile=profile)

    async def get_reputation_role_ids(self, guild_id: int) -> dict[str, int]:
        roles = await self._roles.get_all(guild_id)
        return {
            key: role_id
            for key, role_id in roles.items()
            if key in {GOOD_REPUTATION_ROLE_KEY, BAD_REPUTATION_ROLE_KEY}
        }

    def build_reputation_role_plan(
        self,
        *,
        current_role_ids: set[int],
        configured_role_ids: Mapping[str, int],
        summary: ReputationSummary,
    ) -> ReputationRolePlan:
        ratio = self.reputation_ratio(summary)
        desired_key = GOOD_REPUTATION_ROLE_KEY if ratio >= 1 else BAD_REPUTATION_ROLE_KEY
        desired_role_id = configured_role_ids.get(desired_key)
        managed_role_ids = set(configured_role_ids.values())
        role_ids_to_remove = tuple(
            sorted(role_id for role_id in current_role_ids & managed_role_ids if role_id != desired_role_id)
        )
        role_id_to_add = desired_role_id if desired_role_id and desired_role_id not in current_role_ids else None
        return ReputationRolePlan(
            role_id_to_add=role_id_to_add,
            role_ids_to_remove=role_ids_to_remove,
        )

    @staticmethod
    def normalize_genre(value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().lower()
        if cleaned not in {"homme", "femme", "autre"}:
            return value
        return cleaned.capitalize()

    @staticmethod
    def validate_profile_fields(
        *,
        genre: str | None,
        valorant_tracker: str | None,
        note: str | None,
    ) -> Optional[str]:
        if genre and genre.lower() not in {"homme", "femme", "autre"}:
            return "Le genre doit etre Homme, Femme ou Autre."
        if valorant_tracker and not TRACKER_URL_PATTERN.match(valorant_tracker):
            return "Le lien tracker.gg Valorant est invalide."
        if note and URL_PATTERN.search(note):
            return "La note personnelle ne doit pas contenir de lien."
        return None

    @staticmethod
    def reputation_ratio(summary: ReputationSummary) -> float:
        return (summary.recommendations + 1) / (summary.reports + 1)
