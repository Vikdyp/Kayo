# cogs/role_management/services/language_role_service.py

from __future__ import annotations

import logging
from typing import Optional

from cogs.configuration.services.role_service import RoleConfigurationService
from database.services.persistent_messages_service import (
    PersistentMessagesService,
    PersistentMessageInfo,
)

logger = logging.getLogger(__name__)

PERSISTENT_MSG_TYPE = "language_roles"


class LanguageRoleService:
    """Service métier pour la sélection de rôles de langue."""

    def __init__(
        self,
        role_config_svc: RoleConfigurationService,
        persistent_msg_svc: PersistentMessagesService,
    ):
        self._role_svc = role_config_svc
        self._persistent_msg_svc = persistent_msg_svc

    async def get_role_id(self, guild_id: int, role_name: str) -> Optional[int]:
        return await self._role_svc.get_one(guild_id, role_name)

    async def get_persistent_message(
        self, guild_id: int
    ) -> Optional[PersistentMessageInfo]:
        return await self._persistent_msg_svc.get(guild_id, PERSISTENT_MSG_TYPE)

    async def save_persistent_message(
        self,
        guild_id: int,
        guild_name: Optional[str],
        channel_id: int,
        message_id: int,
    ) -> None:
        await self._persistent_msg_svc.save(
            guild_id, guild_name, PERSISTENT_MSG_TYPE, channel_id, message_id
        )

    async def delete_persistent_message(self, guild_id: int) -> bool:
        return await self._persistent_msg_svc.delete(guild_id, PERSISTENT_MSG_TYPE)
