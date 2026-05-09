from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

from database.services.guild_roles_service import RoleConfigurationService
from database.services.persistent_messages_service import PersistentMessageInfo, PersistentMessagesService


GAME_ROLE_KEYS = ("initiator", "controller", "duelist", "sentinel", "fill")
LANGUAGE_ROLE_KEYS = ("francais", "anglais", "espagnol")
GAME_ROLE_MESSAGE_TYPE = "role_selection"
LANGUAGE_ROLE_MESSAGE_TYPE = "language_roles"


@dataclass(frozen=True, slots=True)
class RoleSelectionPlan:
    role_to_add_id: Optional[int]
    role_ids_to_remove: tuple[int, ...]
    already_selected: bool


class RoleSelectionService:
    """Business service for role selector messages and selection rules."""

    def __init__(
        self,
        role_config_service: RoleConfigurationService,
        persistent_messages_service: PersistentMessagesService,
    ) -> None:
        self._roles = role_config_service
        self._messages = persistent_messages_service

    async def get_configured_role_ids(
        self,
        guild_id: int,
        role_keys: Sequence[str],
    ) -> dict[str, int]:
        configured = await self._roles.get_all(guild_id)
        return {
            key: configured[key]
            for key in role_keys
            if key in configured
        }

    async def get_role_id(self, guild_id: int, role_key: str) -> Optional[int]:
        return await self._roles.get_one(guild_id, role_key)

    def missing_config_keys(
        self,
        configured_role_ids: Mapping[str, int],
        expected_keys: Sequence[str],
    ) -> tuple[str, ...]:
        return tuple(key for key in expected_keys if key not in configured_role_ids)

    def build_exclusive_selection_plan(
        self,
        *,
        current_role_ids: set[int],
        configured_role_ids: Mapping[str, int],
        selected_key: str,
    ) -> RoleSelectionPlan:
        selected_role_id = configured_role_ids[selected_key]
        managed_role_ids = set(configured_role_ids.values())
        role_ids_to_remove = tuple(
            sorted(role_id for role_id in current_role_ids & managed_role_ids if role_id != selected_role_id)
        )
        already_selected = selected_role_id in current_role_ids and not role_ids_to_remove
        return RoleSelectionPlan(
            role_to_add_id=None if selected_role_id in current_role_ids else selected_role_id,
            role_ids_to_remove=role_ids_to_remove,
            already_selected=already_selected,
        )

    def build_toggle_plan(self, *, current_role_ids: set[int], role_id: int) -> RoleSelectionPlan:
        if role_id in current_role_ids:
            return RoleSelectionPlan(
                role_to_add_id=None,
                role_ids_to_remove=(role_id,),
                already_selected=True,
            )
        return RoleSelectionPlan(
            role_to_add_id=role_id,
            role_ids_to_remove=(),
            already_selected=False,
        )

    async def get_persistent_message(
        self,
        guild_id: int,
        message_type: str,
    ) -> Optional[PersistentMessageInfo]:
        return await self._messages.get(guild_id, message_type)

    async def save_persistent_message(
        self,
        *,
        guild_id: int,
        guild_name: Optional[str],
        message_type: str,
        channel_id: int,
        message_id: int,
    ) -> None:
        await self._messages.save(
            guild_id=guild_id,
            guild_name=guild_name,
            message_type=message_type,
            channel_id=channel_id,
            message_id=message_id,
        )

    async def delete_persistent_message(self, guild_id: int, message_type: str) -> bool:
        return await self._messages.delete(guild_id, message_type)
