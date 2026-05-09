from __future__ import annotations

from typing import Optional

from database.services.guild_channels_service import ChannelConfigurationService
from database.services.guild_members_service import GuildMembersService, RulesAcceptanceResult
from database.services.persistent_messages_service import PersistentMessageInfo, PersistentMessagesService


RULES_CHANNEL_KEY = "rules"
RULES_MESSAGE_TYPE = "rules_embed"


class RulesService:
    """Business service for rules acceptance and persistent rules message."""

    def __init__(
        self,
        channel_config_service: ChannelConfigurationService,
        guild_members_service: GuildMembersService,
        persistent_messages_service: PersistentMessagesService,
    ) -> None:
        self._channels = channel_config_service
        self._members = guild_members_service
        self._messages = persistent_messages_service

    async def get_rules_channel_id(self, guild_id: int) -> Optional[int]:
        return await self._channels.get_one(guild_id, RULES_CHANNEL_KEY)

    async def has_accepted_rules(self, *, guild_id: int, discord_user_id: int) -> bool:
        return await self._members.has_accepted_rules(
            guild_id=guild_id,
            discord_user_id=discord_user_id,
        )

    async def accept_rules(
        self,
        *,
        guild_id: int,
        guild_name: Optional[str],
        discord_user_id: int,
    ) -> RulesAcceptanceResult:
        return await self._members.accept_rules(
            guild_id=guild_id,
            guild_name=guild_name,
            discord_user_id=discord_user_id,
        )

    async def get_rules_message(self, guild_id: int) -> Optional[PersistentMessageInfo]:
        return await self._messages.get(guild_id, RULES_MESSAGE_TYPE)

    async def save_rules_message(
        self,
        *,
        guild_id: int,
        guild_name: Optional[str],
        channel_id: int,
        message_id: int,
    ) -> None:
        await self._messages.save(
            guild_id=guild_id,
            guild_name=guild_name,
            message_type=RULES_MESSAGE_TYPE,
            channel_id=channel_id,
            message_id=message_id,
        )

    async def delete_rules_message(self, guild_id: int) -> bool:
        return await self._messages.delete(guild_id, RULES_MESSAGE_TYPE)
