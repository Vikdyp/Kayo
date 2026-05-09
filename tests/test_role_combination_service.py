from __future__ import annotations

import pytest

from cogs.role_management.services import RoleCombinationService
from cogs.role_management.services.role_combination_service import (
    RoleCombinationInfo,
    build_combination,
    sorted_role_pair,
)


class FakeRoleCombinationsDb:
    def __init__(self) -> None:
        self.values: dict[int, dict[tuple[int, int], int]] = {}

    async def list_combinations(self, guild_id: int):
        return [
            RoleCombinationInfo(primary_role_id=a, secondary_role_id=b, combined_role_id=c)
            for (a, b), c in sorted(self.values.get(guild_id, {}).items())
        ]

    async def save_combination(
        self,
        *,
        guild_id: int,
        guild_name: str | None,
        primary_role_id: int,
        secondary_role_id: int,
        combined_role_id: int,
    ) -> None:
        self.values.setdefault(guild_id, {})[(primary_role_id, secondary_role_id)] = combined_role_id

    async def delete_combination(
        self,
        *,
        guild_id: int,
        primary_role_id: int,
        secondary_role_id: int,
    ) -> bool:
        return self.values.setdefault(guild_id, {}).pop((primary_role_id, secondary_role_id), None) is not None


def make_service(db: FakeRoleCombinationsDb | None = None) -> RoleCombinationService:
    return RoleCombinationService(db or FakeRoleCombinationsDb())


def test_sorted_role_pair_is_stable() -> None:
    assert sorted_role_pair(20, 10) == (10, 20)


def test_build_combination_rejects_duplicate_roles() -> None:
    assert build_combination(1, 1, 2) is None
    assert build_combination(1, 2, 1) is None
    assert build_combination(1, 2, 2) is None


@pytest.mark.asyncio
async def test_role_combination_service_saves_lists_and_removes() -> None:
    db = FakeRoleCombinationsDb()
    service = make_service(db)

    saved = await service.save_combination(
        guild_id=1,
        guild_name="Guild",
        primary_role_id=20,
        secondary_role_id=10,
        combined_role_id=30,
    )
    listed = await service.list_combinations(1)
    removed = await service.remove_combination(guild_id=1, primary_role_id=10, secondary_role_id=20)
    missing = await service.remove_combination(guild_id=1, primary_role_id=10, secondary_role_id=20)

    assert saved.status == "saved"
    assert listed == [RoleCombinationInfo(primary_role_id=10, secondary_role_id=20, combined_role_id=30)]
    assert removed.status == "removed"
    assert missing.status == "not_found"


def test_role_combination_assignment_plan_adds_combined_and_removes_sources() -> None:
    service = make_service()

    plan = service.build_assignment_plan(
        current_role_ids={10, 20, 99},
        combinations=[RoleCombinationInfo(primary_role_id=10, secondary_role_id=20, combined_role_id=30)],
    )

    assert plan.role_ids_to_add == (30,)
    assert plan.role_ids_to_remove == (10, 20)


def test_role_combination_assignment_plan_skips_existing_combined_role() -> None:
    service = make_service()

    plan = service.build_assignment_plan(
        current_role_ids={10, 20, 30},
        combinations=[RoleCombinationInfo(primary_role_id=10, secondary_role_id=20, combined_role_id=30)],
    )

    assert plan.role_ids_to_add == ()
    assert plan.role_ids_to_remove == ()
