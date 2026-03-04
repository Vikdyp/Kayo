# cogs/rules/services/rules_service.py
"""
Service métier pour la gestion du règlement.
- Aucun SQL ici
- Délègue aux services DB
"""

import logging
from typing import Optional

from database.services.guild_channels_service import ChannelConfigurationService
from database.services.persistent_messages_service import (
    PersistentMessagesService,
    PersistentMessageInfo,
)
from database.services.guild_members_service import GuildMembersService

logger = logging.getLogger(__name__)

RULES_EMBED_TYPE = "rules_embed"


class RulesService:
    """Service métier pour les fonctionnalités de règlement."""

    def __init__(
        self,
        channel_config_svc: ChannelConfigurationService,
        persistent_msg_svc: PersistentMessagesService,
        guild_members_svc: GuildMembersService,
    ):
        self._channel_config = channel_config_svc
        self._persistent_msg = persistent_msg_svc
        self._guild_members = guild_members_svc

    async def get_rules_channel_id(self, guild_id: int) -> Optional[int]:
        """Récupère l'ID du channel configuré pour les règles."""
        return await self._channel_config.get_one(guild_id, "rules")

    async def has_accepted_rules(self, guild_id: int, discord_id: int) -> bool:
        """Vérifie si un utilisateur a accepté les règles."""
        return await self._guild_members.has_accepted_rules(guild_id, discord_id)

    async def accept_rules(
        self, guild_id: int, guild_name: str, discord_id: int
    ) -> bool:
        """Enregistre l'acceptation des règles par un utilisateur."""
        try:
            return await self._guild_members.accept_rules(
                guild_id, guild_name, discord_id
            )
        except Exception as e:
            logger.error(f"Erreur accept_rules pour discord_id={discord_id}: {e}")
            return False

    async def get_rules_message(
        self, guild_id: int
    ) -> Optional[PersistentMessageInfo]:
        """Récupère l'info du message de règlement persistant."""
        return await self._persistent_msg.get(guild_id, RULES_EMBED_TYPE)

    async def save_rules_message(
        self,
        guild_id: int,
        guild_name: str,
        channel_id: int,
        message_id: int,
    ) -> None:
        """Sauvegarde le message de règlement persistant."""
        await self._persistent_msg.save(
            guild_id, guild_name, RULES_EMBED_TYPE, channel_id, message_id
        )

    async def delete_rules_message(self, guild_id: int) -> bool:
        """Supprime le message de règlement persistant."""
        return await self._persistent_msg.delete(guild_id, RULES_EMBED_TYPE)
