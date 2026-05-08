# cogs/moderation/services/moderation_service.py
"""
Service métier pour la modération.
Aucun accès DB direct - délègue aux DB services.
"""

import logging
from datetime import datetime
from typing import Dict, Optional, List

from database.services.moderation_service import ModerationDbService, BanInfo, WarningInfo
from database.services.persistent_messages_service import PersistentMessagesService
from database.services.guild_roles_service import RoleConfigurationService
from database.services.guild_channels_service import ChannelConfigurationService

logger = logging.getLogger(__name__)


class ModerationService:
    """
    Service métier pour la modération.
    Reçoit les DB services en injection.
    """

    def __init__(
        self,
        moderation_db_svc: ModerationDbService,
        persistent_msg_svc: PersistentMessagesService,
        role_config_svc: RoleConfigurationService,
        channel_config_svc: ChannelConfigurationService,
    ):
        self._mod_db = moderation_db_svc
        self._persistent_msg = persistent_msg_svc
        self._role_config = role_config_svc
        self._channel_config = channel_config_svc

    # ==================== BANS ====================

    async def get_ban_info(self, guild_id: int, discord_user_id: int) -> Optional[BanInfo]:
        """
        Récupère les informations de ban pour un utilisateur.
        Retourne None si l'utilisateur n'est pas banni.
        """
        try:
            return await self._mod_db.get_ban(guild_id, discord_user_id)
        except Exception as e:
            logger.error(f"Erreur get_ban_info pour user {discord_user_id}: {e}")
            return None

    async def add_ban(
        self,
        guild_id: int,
        guild_name: Optional[str],
        user_id: int,
        ban_type: str,
        reason: str,
        banned_by: int,
        ban_end: Optional[datetime],
    ) -> bool:
        """
        Ajoute ou met à jour un bannissement.
        Retourne True si l'opération réussit.
        """
        try:
            await self._mod_db.add_ban(
                guild_id=guild_id,
                guild_name=guild_name,
                target_discord_id=user_id,
                moderator_discord_id=banned_by,
                ban_type=ban_type,
                reason=reason,
                ban_end=ban_end,
            )
            logger.info(f"Ban ajouté pour user {user_id} dans guild {guild_id}")
            return True
        except ValueError as e:
            logger.error(f"Validation error add_ban: {e}")
            return False
        except Exception as e:
            logger.error(f"Erreur add_ban pour user {user_id}: {e}")
            return False

    async def remove_ban(self, guild_id: int, user_id: int) -> bool:
        """
        Supprime un bannissement.
        Retourne True si l'opération réussit.
        """
        try:
            result = await self._mod_db.remove_ban(guild_id, user_id)
            if result:
                logger.info(f"Ban supprimé pour user {user_id} dans guild {guild_id}")
            return result
        except Exception as e:
            logger.error(f"Erreur remove_ban pour user {user_id}: {e}")
            return False

    async def get_expired_bans(self, current_time: datetime) -> List[BanInfo]:
        """
        Récupère les bannissements temporaires expirés.
        """
        try:
            return await self._mod_db.get_expired_bans(current_time)
        except Exception as e:
            logger.error(f"Erreur get_expired_bans: {e}")
            return []

    # ==================== WARNINGS ====================

    async def get_warnings(self, guild_id: int, user_id: int) -> int:
        """
        Récupère le nombre d'avertissements d'un utilisateur.
        """
        try:
            return await self._mod_db.get_warning_count(guild_id, user_id)
        except Exception as e:
            logger.error(f"Erreur get_warnings pour user {user_id}: {e}")
            return 0

    async def add_warning(
        self,
        guild_id: int,
        guild_name: Optional[str],
        user_id: int,
        warned_by: int,
        reason: Optional[str] = None,
    ) -> bool:
        """
        Ajoute un avertissement à un utilisateur.
        Retourne True si l'opération réussit.
        """
        try:
            await self._mod_db.add_warning(
                guild_id=guild_id,
                guild_name=guild_name,
                target_discord_id=user_id,
                moderator_discord_id=warned_by,
                reason=reason,
            )
            logger.info(f"Warning ajouté pour user {user_id} dans guild {guild_id}")
            return True
        except Exception as e:
            logger.error(f"Erreur add_warning pour user {user_id}: {e}")
            return False

    async def list_warnings(
        self,
        guild_id: int,
        user_id: int,
        limit: int = 50,
    ) -> List[WarningInfo]:
        """
        Liste les avertissements d'un utilisateur.
        """
        try:
            return await self._mod_db.list_warnings(guild_id, user_id, limit)
        except Exception as e:
            logger.error(f"Erreur list_warnings pour user {user_id}: {e}")
            return []

    async def delete_warning(self, warning_id: int) -> bool:
        """
        Supprime un avertissement par ID.
        """
        try:
            return await self._mod_db.delete_warning(warning_id)
        except Exception as e:
            logger.error(f"Erreur delete_warning pour warning {warning_id}: {e}")
            return False

    async def clear_warnings(self, guild_id: int, user_id: int) -> int:
        """
        Supprime tous les avertissements d'un utilisateur.
        Retourne le nombre supprimé.
        """
        try:
            return await self._mod_db.clear_warnings(guild_id, user_id)
        except Exception as e:
            logger.error(f"Erreur clear_warnings pour user {user_id}: {e}")
            return 0

    # ==================== ROLE BACKUPS ====================

    async def get_roles_backup(self, guild_id: int, discord_user_id: int) -> List[int]:
        """
        Récupère les rôles sauvegardés d'un utilisateur.
        """
        try:
            roles = await self._mod_db.get_roles(guild_id, discord_user_id)
            return roles if roles else []
        except Exception as e:
            logger.error(f"Erreur get_roles_backup pour user {discord_user_id}: {e}")
            return []

    async def update_roles_backup(
        self,
        guild_id: int,
        guild_name: Optional[str],
        discord_user_id: int,
        roles: List[int],
    ) -> bool:
        """
        Met à jour le backup des rôles d'un utilisateur.
        """
        try:
            return await self._mod_db.save_roles(
                guild_id=guild_id,
                guild_name=guild_name,
                target_discord_id=discord_user_id,
                roles=roles,
            )
        except Exception as e:
            logger.error(f"Erreur update_roles_backup pour user {discord_user_id}: {e}")
            return False

    async def clear_roles_backup(self, guild_id: int, discord_user_id: int) -> bool:
        """
        Efface le backup des rôles d'un utilisateur.
        """
        try:
            return await self._mod_db.clear_roles(guild_id, discord_user_id)
        except Exception as e:
            logger.error(f"Erreur clear_roles_backup pour user {discord_user_id}: {e}")
            return False

    # ==================== ROLE CONFIGURATION ====================

    async def get_ban_role_id(self, guild_id: int) -> Optional[int]:
        """
        Récupère l'ID du rôle 'ban' pour un serveur.
        """
        try:
            return await self._role_config.get_one(guild_id, "ban")
        except Exception as e:
            logger.error(f"Erreur get_ban_role_id pour guild {guild_id}: {e}")
            return None

    async def get_role_id_by_name(self, guild_id: int, role_name: str) -> Optional[int]:
        """
        Récupère l'ID d'un rôle par son nom (clé) pour un serveur.
        """
        try:
            return await self._role_config.get_one(guild_id, role_name)
        except Exception as e:
            logger.error(f"Erreur get_role_id_by_name '{role_name}' pour guild {guild_id}: {e}")
            return None

    # ==================== CHANNEL CONFIGURATION ====================

    async def get_moderation_channel_id(self, guild_id: int) -> Optional[int]:
        """
        Récupère l'ID du salon de modération.
        """
        try:
            return await self._channel_config.get_one(guild_id, "modération")
        except Exception as e:
            logger.error(f"Erreur get_moderation_channel_id pour guild {guild_id}: {e}")
            return None

    async def get_deban_channel_id(self, guild_id: int) -> Optional[int]:
        """
        Récupère l'ID du salon de demande-deban.
        """
        try:
            return await self._channel_config.get_one(guild_id, "demande-deban")
        except Exception as e:
            logger.error(f"Erreur get_deban_channel_id pour guild {guild_id}: {e}")
            return None

    async def get_deban_category_id(self, guild_id: int) -> Optional[int]:
        """
        Récupère l'ID de la catégorie pour les demandes de déban.
        """
        try:
            return await self._channel_config.get_one(guild_id, "deban_category")
        except Exception as e:
            logger.error(f"Erreur get_deban_category_id pour guild {guild_id}: {e}")
            return None

    # ==================== PERSISTENT MESSAGES ====================

    async def get_persistent_message(
        self,
        guild_id: int,
        message_type: str,
    ) -> Optional[Dict[str, int]]:
        """
        Récupère un message persistant.
        """
        try:
            info = await self._persistent_msg.get(guild_id, message_type)
            if not info:
                return None
            return {
                "channel_id": info.channel_id,
                "message_id": info.message_id,
            }
        except Exception as e:
            logger.error(f"Erreur get_persistent_message '{message_type}' pour guild {guild_id}: {e}")
            return None

    async def save_persistent_message(
        self,
        guild_id: int,
        guild_name: Optional[str],
        message_type: str,
        channel_id: int,
        message_id: int,
    ) -> bool:
        """
        Enregistre ou met à jour un message persistant.
        """
        try:
            await self._persistent_msg.save(
                guild_id=guild_id,
                guild_name=guild_name,
                message_type=message_type,
                channel_id=channel_id,
                message_id=message_id,
            )
            return True
        except Exception as e:
            logger.error(f"Erreur save_persistent_message '{message_type}' pour guild {guild_id}: {e}")
            return False

    async def delete_persistent_message(
        self,
        guild_id: int,
        message_type: str,
    ) -> bool:
        """
        Supprime un message persistant.
        """
        try:
            return await self._persistent_msg.delete(guild_id, message_type)
        except Exception as e:
            logger.error(f"Erreur delete_persistent_message '{message_type}' pour guild {guild_id}: {e}")
            return False
