from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from database.services.role_combinations_service import RoleCombinationsDbService

RoleCombinationStatus = Literal["saved", "removed", "not_found", "invalid"]


@dataclass(frozen=True, slots=True)
class RoleCombinationInfo:
    primary_role_id: int
    secondary_role_id: int
    combined_role_id: int


@dataclass(frozen=True, slots=True)
class RoleCombinationMutationResult:
    status: RoleCombinationStatus
    combination: RoleCombinationInfo | None = None


@dataclass(frozen=True, slots=True)
class RoleCombinationAssignmentPlan:
    role_ids_to_add: tuple[int, ...]
    role_ids_to_remove: tuple[int, ...]


class RoleCombinationService:
    def __init__(self, db_service: RoleCombinationsDbService) -> None:
        self._db = db_service

    async def list_combinations(self, guild_id: int) -> list[RoleCombinationInfo]:
        rows = await self._db.list_combinations(guild_id)
        return [
            RoleCombinationInfo(
                primary_role_id=row.primary_role_id,
                secondary_role_id=row.secondary_role_id,
                combined_role_id=row.combined_role_id,
            )
            for row in rows
        ]

    async def save_combination(
        self,
        *,
        guild_id: int,
        guild_name: str | None,
        primary_role_id: int,
        secondary_role_id: int,
        combined_role_id: int,
    ) -> RoleCombinationMutationResult:
        combination = build_combination(primary_role_id, secondary_role_id, combined_role_id)
        if combination is None:
            return RoleCombinationMutationResult(status="invalid")
        await self._db.save_combination(
            guild_id=guild_id,
            guild_name=guild_name,
            primary_role_id=combination.primary_role_id,
            secondary_role_id=combination.secondary_role_id,
            combined_role_id=combination.combined_role_id,
        )
        return RoleCombinationMutationResult(status="saved", combination=combination)

    async def remove_combination(
        self,
        *,
        guild_id: int,
        primary_role_id: int,
        secondary_role_id: int,
    ) -> RoleCombinationMutationResult:
        primary_role_id, secondary_role_id = sorted_role_pair(primary_role_id, secondary_role_id)
        removed = await self._db.delete_combination(
            guild_id=guild_id,
            primary_role_id=primary_role_id,
            secondary_role_id=secondary_role_id,
        )
        return RoleCombinationMutationResult(status="removed" if removed else "not_found")

    def build_assignment_plan(
        self,
        *,
        current_role_ids: set[int],
        combinations: list[RoleCombinationInfo],
    ) -> RoleCombinationAssignmentPlan:
        role_ids_to_add: set[int] = set()
        role_ids_to_remove: set[int] = set()

        for combination in combinations:
            has_primary = combination.primary_role_id in current_role_ids
            has_secondary = combination.secondary_role_id in current_role_ids
            has_combined = combination.combined_role_id in current_role_ids

            if has_primary and has_secondary and not has_combined:
                role_ids_to_add.add(combination.combined_role_id)
                role_ids_to_remove.update((combination.primary_role_id, combination.secondary_role_id))

        role_ids_to_remove.difference_update(role_ids_to_add)
        return RoleCombinationAssignmentPlan(
            role_ids_to_add=tuple(sorted(role_ids_to_add)),
            role_ids_to_remove=tuple(sorted(role_ids_to_remove)),
        )


def build_combination(
    primary_role_id: int,
    secondary_role_id: int,
    combined_role_id: int,
) -> RoleCombinationInfo | None:
    primary_role_id, secondary_role_id = sorted_role_pair(primary_role_id, secondary_role_id)
    if primary_role_id == secondary_role_id:
        return None
    if combined_role_id in {primary_role_id, secondary_role_id}:
        return None
    return RoleCombinationInfo(
        primary_role_id=primary_role_id,
        secondary_role_id=secondary_role_id,
        combined_role_id=combined_role_id,
    )


def sorted_role_pair(first_role_id: int, second_role_id: int) -> tuple[int, int]:
    if first_role_id <= second_role_id:
        return first_role_id, second_role_id
    return second_role_id, first_role_id
